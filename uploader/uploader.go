package uploader

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/google/uuid"
)

type RutubeUploader struct {
	client    *http.Client
	csrfToken string
	userID    string
	jwt       string
	dryRun    bool
}

type CookieInfo struct {
	CSRFToken string
	UserID    string
	JWT       string
}

func ParseNetscapeCookies(path string) ([]*http.Cookie, *CookieInfo, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer file.Close()

	var cookies []*http.Cookie
	info := &CookieInfo{}

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "#") || strings.TrimSpace(line) == "" {
			continue
		}

		parts := strings.Split(line, "\t")
		if len(parts) < 7 {
			continue
		}

		// domain, flag, path, secure, expiration, name, value
		name := parts[5]
		value := parts[6]

		cookie := &http.Cookie{
			Name:  name,
			Value: value,
		}
		cookies = append(cookies, cookie)

		switch name {
		case "csrftoken":
			info.CSRFToken = value
		case "visitorID":
			info.UserID = value
		case "jwt":
			info.JWT = value
		}
	}

	return cookies, info, scanner.Err()
}

func NewRutubeUploader(cookiePath string, dryRun bool) (*RutubeUploader, error) {
	cookies, info, err := ParseNetscapeCookies(cookiePath)
	if err != nil {
		return nil, err
	}

	if info.CSRFToken == "" {
		return nil, fmt.Errorf("csrftoken not found in cookies")
	}

	jar, _ := NewCookieJar(cookies)
	client := &http.Client{
		Jar: jar,
	}

	return &RutubeUploader{
		client:    client,
		csrfToken: info.CSRFToken,
		userID:    info.UserID,
		jwt:       info.JWT,
		dryRun:    dryRun,
	}, nil
}

type simpleJar struct {
	cookies map[string][]*http.Cookie
}

func (j *simpleJar) SetCookies(u *url.URL, cookies []*http.Cookie) {
	j.cookies[u.Host] = cookies
}

func (j *simpleJar) Cookies(u *url.URL) []*http.Cookie {
	// For simplicity, return all cookies that match the domain suffix
	var res []*http.Cookie
	for host, cookies := range j.cookies {
		if strings.HasSuffix(u.Host, host) || strings.HasSuffix(host, u.Host) {
			res = append(res, cookies...)
		}
	}
	return res
}

func NewCookieJar(initialCookies []*http.Cookie) (http.CookieJar, error) {
	jar := &simpleJar{cookies: make(map[string][]*http.Cookie)}
	// Group by a sensible default host if not provided, or just store all
	jar.cookies["rutube.ru"] = initialCookies
	return jar, nil
}

func (u *RutubeUploader) CreateUploadSession() (string, string, error) {
	if u.dryRun {
		return "dry_run_" + uuid.New().String(), "dry_run_" + uuid.New().String(), nil
	}

	batchID := strings.ReplaceAll(uuid.New().String(), "-", "")
	apiURL := "https://studio.rutube.ru/api/uploader/upload_session/"

	params := url.Values{}
	params.Add("client", "vulp")
	params.Add("batch_id", batchID)

	fullURL := apiURL + "?" + params.Encode()

	payload := map[string]interface{}{
		"cancelToken": map[string]interface{}{
			"promise": map[string]interface{}{},
		},
	}
	body, _ := json.Marshal(payload)

	req, _ := http.NewRequest("POST", fullURL, bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-CSRFToken", u.csrfToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")
	req.Header.Set("Origin", "https://studio.rutube.ru")
	req.Header.Set("Referer", "https://studio.rutube.ru/")

	resp, err := u.client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", "", fmt.Errorf("failed to create session: status %d", resp.StatusCode)
	}

	var result struct {
		SID   string `json:"sid"`
		Video string `json:"video"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", "", err
	}

	return result.SID, result.Video, nil
}

func (u *RutubeUploader) InitTUS(sessionID, videoID, filename string, size int64) error {
	if u.dryRun {
		return nil
	}

	tusURL := fmt.Sprintf("https://u.rutube.ru/upload/%s", sessionID)

	metadata := fmt.Sprintf("sessionId %s,videoId %s,userId %s,uploadSessionId %s",
		base64.StdEncoding.EncodeToString([]byte(sessionID)),
		base64.StdEncoding.EncodeToString([]byte(videoID)),
		base64.StdEncoding.EncodeToString([]byte(u.userID)),
		base64.StdEncoding.EncodeToString([]byte(fmt.Sprintf("%s::user-%s::%sZ", filename, u.userID, time.Now().Format("2006-01-02T15:04:05.000")))),
	)

	req, _ := http.NewRequest("POST", tusURL, nil)
	req.Header.Set("Content-Type", "application/offset+octet-stream")
	req.Header.Set("Tus-Resumable", "1.0.0")
	req.Header.Set("Upload-Length", fmt.Sprintf("%d", size))
	req.Header.Set("Upload-Metadata", metadata)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

	resp, err := u.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("failed to init TUS: status %d", resp.StatusCode)
	}

	return nil
}

func (u *RutubeUploader) UploadData(sessionID string, data io.Reader, size int64) error {
	if u.dryRun {
		return nil
	}

	tusURL := fmt.Sprintf("https://u.rutube.ru/upload/%s", sessionID)

	req, _ := http.NewRequest("PATCH", tusURL, data)
	req.Header.Set("Content-Type", "application/offset+octet-stream")
	req.Header.Set("Tus-Resumable", "1.0.0")
	req.Header.Set("Upload-Offset", "0")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")
	req.ContentLength = size

	resp, err := u.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("failed to upload data: status %d", resp.StatusCode)
	}

	return nil
}

func (u *RutubeUploader) Publish(videoID, title, description string, category string) (string, error) {
	if u.dryRun {
		return fmt.Sprintf("https://rutube.ru/video/%s/", videoID), nil
	}

	publishURL := fmt.Sprintf("https://studio.rutube.ru/api/v2/video/%s/?client=vulp", videoID)

	payload := map[string]interface{}{
		"title":       title,
		"description": description,
		"is_hidden":   false,
		"is_adult":    false,
		"category":    category,
		"properties": map[string]interface{}{
			"hide_comments": false,
		},
	}
	body, _ := json.Marshal(payload)

	req, _ := http.NewRequest("PATCH", publishURL, bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-CSRFToken", u.csrfToken)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

	resp, err := u.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("failed to publish: status %d", resp.StatusCode)
	}

	var result struct {
		VideoURL string `json:"video_url"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}

	return result.VideoURL, nil
}

func (u *RutubeUploader) FullUpload(path string, title, description, category string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	stat, _ := file.Stat()
	size := stat.Size()
	filename := filepath.Base(path)

	sid, vid, err := u.CreateUploadSession()
	if err != nil {
		return "", err
	}

	err = u.InitTUS(sid, vid, filename, size)
	if err != nil {
		return "", err
	}

	err = u.UploadData(sid, file, size)
	if err != nil {
		return "", err
	}

	return u.Publish(vid, title, description, category)
}

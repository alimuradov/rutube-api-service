package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
	"github.com/nezort11/rutube-service/uploader"
)

func main() {
	// Check for cookies file
	cookiePath := "cookies.txt"
	if _, err := os.Stat(cookiePath); os.IsNotExist(err) {
		log.Printf("Warning: %s not found. Server may fail to initialize uploader.", cookiePath)
	}

	r := gin.Default()

	// Serve static files
	r.Static("/static", "./static")
	r.StaticFile("/", "./static/index.html")

	// Max upload size (e.g., 2GB)
	r.MaxMultipartMemory = 2 << 30

	r.POST("/upload", func(c *gin.Context) {
		// Get form data
		title := c.PostForm("title")
		description := c.PostForm("description")
		category := c.PostForm("category")
		file, err := c.FormFile("video")
		if err != nil {
			c.String(http.StatusBadRequest, "No video file provided")
			return
		}

		if title == "" {
			c.String(http.StatusBadRequest, "Title is required")
			return
		}

		// Save file temporarily
		tempDir := filepath.Join(".", "temp")
		os.MkdirAll(tempDir, 0755)
		tempPath := filepath.Join(tempDir, file.Filename)
		if err := c.SaveUploadedFile(file, tempPath); err != nil {
			c.String(http.StatusInternalServerError, "Failed to save temporary file")
			return
		}
		defer os.Remove(tempPath)

		// Initialize uploader
		// Using dryRun false by default, can be toggled via env
		dryRun := os.Getenv("DRY_RUN") == "true"
		rutube, err := uploader.NewRutubeUploader(cookiePath, dryRun)
		if err != nil {
			c.String(http.StatusInternalServerError, fmt.Sprintf("Failed to initialize uploader: %v", err))
			return
		}

		// Upload and publish
		log.Printf("Starting upload: %s (Title: %s)", file.Filename, title)
		videoURL, err := rutube.FullUpload(tempPath, title, description, category)
		if err != nil {
			log.Printf("Upload failed: %v", err)
			c.String(http.StatusInternalServerError, fmt.Sprintf("Upload failed: %v", err))
			return
		}

		log.Printf("Upload successful: %s", videoURL)
		c.JSON(http.StatusOK, gin.H{
			"url": videoURL,
		})
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	fmt.Printf("\n🚀 Rutube Studio Server running on http://localhost:%s\n", port)
	r.Run(":" + port)
}

package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
	"github.com/golang-jwt/jwt/v5"
	"github.com/joho/godotenv"
	"golang.org/x/crypto/bcrypt"
)

var (
	db        *sql.DB
	jwtSecret []byte
	backend   *httputil.ReverseProxy
)

// ─── 数据模型 ───

type User struct {
	ID        int       `json:"id"`
	Username  string    `json:"username"`
	Email     string    `json:"email"`
	CreatedAt time.Time `json:"created_at"`
}

type RegisterRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Email    string `json:"email"`
}

type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type AuthResponse struct {
	Token string `json:"token"`
	User  User   `json:"user"`
}

type ErrorResponse struct {
	Error string `json:"error"`
}

// ─── 初始化数据库 ───

func initDB() {
	dsn := os.Getenv("MYSQL_DSN")
	if dsn == "" {
		dsn = "root:quantum123@tcp(localhost:3306)/quantum_auth?parseTime=true"
	}

	var err error
	for i := 0; i < 30; i++ {
		db, err = sql.Open("mysql", dsn)
		if err == nil {
			err = db.Ping()
		}
		if err == nil {
			break
		}
		log.Printf("[auth] 等待 MySQL 就绪 (%d/30)...", i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatalf("[auth] MySQL 连接失败: %v", err)
	}

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS users (
			id INT AUTO_INCREMENT PRIMARY KEY,
			username VARCHAR(64) UNIQUE NOT NULL,
			password_hash VARCHAR(255) NOT NULL,
			email VARCHAR(128) DEFAULT '',
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		log.Fatalf("[auth] 建表失败: %v", err)
	}
	log.Println("[auth] MySQL 已连接，用户表就绪")
}

// ─── 注册 ───

func handleRegister(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{"请求格式错误"})
		return
	}

	if len(req.Username) < 3 || len(req.Password) < 6 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{"用户名至少3位，密码至少6位"})
		return
	}

	// 检查用户名是否已存在
	var existingID int
	err := db.QueryRow("SELECT id FROM users WHERE username = ?", req.Username).Scan(&existingID)
	if err == nil {
		writeJSON(w, http.StatusConflict, ErrorResponse{"该用户名已注册，请直接登录或更换用户名"})
		return
	}

	// 如果提供了邮箱，检查邮箱是否已存在
	if req.Email != "" {
		err := db.QueryRow("SELECT id FROM users WHERE email = ?", req.Email).Scan(&existingID)
		if err == nil {
			writeJSON(w, http.StatusConflict, ErrorResponse{"该邮箱已被注册，请直接登录或更换邮箱"})
			return
		}
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{"密码加密失败"})
		return
	}

	result, err := db.Exec("INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
		req.Username, string(hash), req.Email)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{"注册失败"})
		return
	}

	id, _ := result.LastInsertId()
	token, _ := generateToken(int(id), req.Username)

	log.Printf("[auth] 新用户注册: %s (id=%d)", req.Username, id)
	writeJSON(w, http.StatusCreated, AuthResponse{
		Token: token,
		User:  User{ID: int(id), Username: req.Username, Email: req.Email},
	})
}

// ─── 登录 ───

func handleLogin(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{"请求格式错误"})
		return
	}

	var user User
	var hash string
	err := db.QueryRow("SELECT id, username, email, password_hash FROM users WHERE username = ?",
		req.Username).Scan(&user.ID, &user.Username, &user.Email, &hash)
	if err == sql.ErrNoRows {
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{"用户名或密码错误"})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{"查询失败"})
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(req.Password)); err != nil {
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{"用户名或密码错误"})
		return
	}

	token, _ := generateToken(user.ID, user.Username)
	log.Printf("[auth] 用户登录: %s", req.Username)
	writeJSON(w, http.StatusOK, AuthResponse{Token: token, User: user})
}

// ─── JWT ───

func generateToken(userID int, username string) (string, error) {
	claims := jwt.MapClaims{
		"user_id":  userID,
		"username": username,
		"exp":      time.Now().Add(72 * time.Hour).Unix(),
		"iat":      time.Now().Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(jwtSecret)
}

func validateToken(tokenStr string) (jwt.MapClaims, error) {
	token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
		return jwtSecret, nil
	})
	if err != nil || !token.Valid {
		return nil, err
	}
	return token.Claims.(jwt.MapClaims), nil
}

// ─── 反向代理到 FastAPI ───

func proxyHandler(w http.ResponseWriter, r *http.Request) {
	// 添加用户信息到 header 传给 Python
	tokenStr := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if claims, err := validateToken(tokenStr); err == nil {
		r.Header.Set("X-User-ID", fmt.Sprintf("%.0f", claims["user_id"].(float64)))
		r.Header.Set("X-Username", claims["username"].(string))
	}
	backend.ServeHTTP(w, r)
}

// ─── 全局路由 ───

func mainHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

	if r.Method == "OPTIONS" {
		w.WriteHeader(http.StatusOK)
		return
	}

	path := r.URL.Path

	// 公开：认证接口
	switch path {
	case "/api/auth/register":
		handleRegister(w, r)
		return
	case "/api/auth/login":
		handleLogin(w, r)
		return
	}

	// 其余 /api/* 需要登录
	if strings.HasPrefix(path, "/api/") {
		tokenStr := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		if _, err := validateToken(tokenStr); err != nil {
			writeJSON(w, http.StatusUnauthorized, ErrorResponse{"请先登录"})
			return
		}
		proxyHandler(w, r)
		return
	}

	// 前端页面直接转发
	proxyHandler(w, r)
}

// ─── 辅助函数 ───

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func main() {
	// 加载 .env 文件（如果存在），命令行环境变量优先级更高
	_ = godotenv.Load("../.env")
	_ = godotenv.Load(".env")

	jwtSecret = []byte(os.Getenv("JWT_SECRET"))
	if len(jwtSecret) == 0 {
		jwtSecret = []byte("change-me-in-production-use-a-long-random-string")
	}

	initDB()

	backendURL := os.Getenv("BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://localhost:8000"
	}
	u, _ := url.Parse(backendURL)
	backend = httputil.NewSingleHostReverseProxy(u)

	log.Printf("[auth] 服务启动 :8080 → %s", backendURL)
	if err := http.ListenAndServe(":8080", http.HandlerFunc(mainHandler)); err != nil {
		log.Fatalf("[auth] 启动失败: %v", err)
	}
}

package config

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

type Config struct {
	Auth   AuthConfig
	Logger LoggerConfig
}
type AuthConfig struct {
	Handler HandlerConfig
	Server  ServerConfig

	UserRepo         UserRepoConfig
	RefreshTokenRepo RefreshTokenRepoConfig

	JWT    JWTConfig
	Argon2 Argon2Config
	SHA256 SHA256Config
}
type HandlerConfig struct {
	TimeContextInSecond int
	RefreshTTLDays      int
}
type ServerConfig struct {
	Port string
}
type UserRepoConfig struct {
	Path string
	// MaxUsers caps how many accounts may exist. 0 disables the check.
	// Register returns ErrUserLimitReached once this many users are stored.
	MaxUsers int
}
type RefreshTokenRepoConfig struct {
	Path string
	// MaxPerUser caps live refresh tokens per account. 0 disables the cap.
	// A resource guard, not a security control: every successful login adds
	// a token, and a user who never logs out would otherwise append one per
	// login forever, each entry rewritten to disk on every save. The
	// tokens themselves are already bounded by expiry and revocation.
	MaxPerUser int
}

type JWTConfig struct {
	PrivateKey *rsa.PrivateKey
	PublicKey  *rsa.PublicKey

	AccessTTLMinutes int
	RefreshTTLDays   int
	Issuer           string
}

type Argon2Config struct {
	Memory      uint32
	Iterations  uint32
	Parallelism uint8
	SaltLength  uint32
	KeyLength   uint32
	Pepper      string
}

type SHA256Config struct {
	Salt []byte
}

type LoggerConfig struct {
	Level  string
	Format string
}

func Load() (*Config, error) {
	_ = godotenv.Load(".env")

	privateKeyPath := getEnv("JWT_PRIVATE_KEY_PATH", "keys/private.pem")
	publicKeyPath := getEnv("JWT_PUBLIC_KEY_PATH", "keys/public.pem")
	privateKey, publicKey := loadOrGenerateKeyPair(privateKeyPath, publicKeyPath)

	keysDir := filepath.Dir(privateKeyPath)

	// Pepper and salt follow the same rule as the RSA keypair: an explicit
	// environment value wins; otherwise the secret lives in a file next to
	// the keys and is created on first start. Keeping them off .env means a
	// lost .env cannot silently change every stored password hash, and one
	// backup of keys/ captures every secret the service owns.
	pepper := getEnv("AUTH_ARGON2_PEPPER", "")
	if pepper == "" {
		pepper = loadOrGeneratePepper(keysDir)
	}
	salt := getEnvAsBase64("AUTH_SHA256_SALT", nil)
	if len(salt) == 0 {
		salt = loadOrGenerateSalt(keysDir)
	}

	return &Config{
		Auth: AuthConfig{
			Handler: HandlerConfig{
				TimeContextInSecond: getEnvAsInt("AUTH_TIME_CONTEXT_IN_SECOND", 15),
				RefreshTTLDays:      getEnvAsInt("AUTH_JWT_REFRESH_TTL_DAYS", 30),
			},
			Server: ServerConfig{
				Port: getEnv("AUTH_SERVER_PORT", "8081"),
			},
			UserRepo: UserRepoConfig{
				Path:     getEnv("AUTH_USER_REPO_PATH", ""),
				MaxUsers: getEnvAsInt("AUTH_MAX_USERS", 10),
			},
			RefreshTokenRepo: RefreshTokenRepoConfig{
				Path:       getEnv("AUTH_REFRESH_TOKEN_REPO_PATH", ""),
				MaxPerUser: getEnvAsInt("AUTH_MAX_REFRESH_TOKENS_PER_USER", 5),
			},
			JWT: JWTConfig{
				PrivateKey:       privateKey,
				PublicKey:        publicKey,
				AccessTTLMinutes: getEnvAsInt("AUTH_JWT_ACCESS_TTL_MINUTE", 15),
				RefreshTTLDays:   getEnvAsInt("AUTH_JWT_REFRESH_TTL_DAYS", 30),
				Issuer:           getEnv("AUTH_JWT_ISSUER", "loregraph-auth-service"),
			},
			Argon2: Argon2Config{
				Iterations:  getEnvAsUint32("AUTH_ARGON2_TIME", 1),
				Memory:      getEnvAsUint32("AUTH_ARGON2_MEMORY", 64*1024),
				Parallelism: getEnvAsUint8("AUTH_ARGON2_THREADS", 4),
				SaltLength:  getEnvAsUint32("AUTH_ARGON2_SALT_LEN", 32),
				KeyLength:   getEnvAsUint32("AUTH_ARGON2_KEY_LEN", 32),

				Pepper: pepper,
			},
			SHA256: SHA256Config{
				Salt: salt,
			},
		},
		Logger: LoggerConfig{
			Level:  getEnv("LOG_LEVEL", "info"),
			Format: getEnv("LOG_FORMAT", "text"),
		},
	}, nil
}

func getEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}
func getEnvAsInt(key string, defaultValue int) int {
	if value, exists := os.LookupEnv(key); exists {
		if parsed, err := strconv.ParseInt(value, 10, strconv.IntSize); err == nil {
			return int(parsed)
		}
	}
	return defaultValue
}

func getEnvAsUint32(key string, defaultValue uint32) uint32 {
	if value, exists := os.LookupEnv(key); exists {
		if parsed, err := strconv.ParseUint(value, 10, 32); err == nil {
			return uint32(parsed)
		}
	}
	return defaultValue
}

func getEnvAsUint8(key string, defaultValue uint8) uint8 {
	if value, exists := os.LookupEnv(key); exists {
		if parsed, err := strconv.ParseUint(value, 10, 8); err == nil {
			return uint8(parsed)
		}
	}
	return defaultValue
}

func getEnvAsBase64(key string, defaultValue []byte) []byte {
	value, exists := os.LookupEnv(key)
	if !exists || value == "" {
		return nil
	}

	if b, err := base64.RawURLEncoding.DecodeString(value); err == nil {
		return b
	}
	if b, err := base64.StdEncoding.DecodeString(value); err == nil {
		return b
	}
	return defaultValue
}

// loadOrGenerateKeyPair returns the RSA keypair the service signs with,
// creating one on disk on first start.
//
// The tokens this service issues live longer than any single run of the
// process, so a fresh pair on every boot would invalidate every session the
// moment the service restarts — the keys must persist. Three cases:
//
//   - Both files present: load and return.
//   - Private present, public missing: derive the public key from the
//     private one. Previously issued tokens still verify because the
//     keypair itself is unchanged.
//   - Private missing: generate a fresh pair and overwrite both. If a public
//     file was there, it belonged to a private key we no longer have — the
//     pair is broken either way, and keeping the orphan would only make the
//     failure harder to diagnose.
func loadOrGenerateKeyPair(privatePath, publicPath string) (*rsa.PrivateKey, *rsa.PublicKey) {
	priv, privErr := tryLoadPrivateKey(privatePath)
	pub, pubErr := tryLoadPublicKey(publicPath)
	if privErr == nil && pubErr == nil {
		return priv, pub
	}

	if privErr == nil {
		if err := writePublicKey(publicPath, &priv.PublicKey); err != nil {
			panic(fmt.Errorf("failed to write %s: %w", publicPath, err))
		}
		return priv, &priv.PublicKey
	}

	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		panic(fmt.Errorf("failed to generate RSA key: %w", err))
	}
	if err := writePrivateKey(privatePath, key); err != nil {
		panic(fmt.Errorf("failed to write %s: %w", privatePath, err))
	}
	if err := writePublicKey(publicPath, &key.PublicKey); err != nil {
		panic(fmt.Errorf("failed to write %s: %w", publicPath, err))
	}
	return key, &key.PublicKey
}

func tryLoadPrivateKey(path string) (*rsa.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("no PEM block in %s", path)
	}
	if key, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return key, nil
	}
	keyAny, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	key, ok := keyAny.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("not RSA private key in %s", path)
	}
	return key, nil
}

func tryLoadPublicKey(path string) (*rsa.PublicKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("no PEM block in %s", path)
	}
	if key, err := x509.ParsePKCS1PublicKey(block.Bytes); err == nil {
		return key, nil
	}
	pubAny, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	pub, ok := pubAny.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("not RSA public key in %s", path)
	}
	return pub, nil
}

func writePrivateKey(path string, key *rsa.PrivateKey) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(key),
	})
	return os.WriteFile(path, pemBytes, 0o600)
}

func writePublicKey(path string, key *rsa.PublicKey) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	der, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		return err
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: der,
	})
	return os.WriteFile(path, pemBytes, 0o644)
}

// loadOrGeneratePepper reads keys/argon2_pepper.b64 (base64 of 32 random
// bytes), or creates it on first start. Returned as a string of the decoded
// bytes, matching what an explicit AUTH_ARGON2_PEPPER would supply.
func loadOrGeneratePepper(keysDir string) string {
	path := filepath.Join(keysDir, "argon2_pepper.b64")
	if raw, ok := readSecretFile(path); ok {
		return string(raw)
	}
	raw := randomBytes(64)
	writeSecretFile(path, raw)
	return string(raw)
}

func loadOrGenerateSalt(keysDir string) []byte {
	path := filepath.Join(keysDir, "sha256_salt.b64")
	if raw, ok := readSecretFile(path); ok {
		return raw
	}
	raw := randomBytes(64)
	writeSecretFile(path, raw)
	return raw
}

func readSecretFile(path string) ([]byte, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(string(data)))
	if err != nil || len(raw) == 0 {
		return nil, false
	}
	return raw, true
}

func writeSecretFile(path string, raw []byte) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		panic(fmt.Errorf("mkdir for %s: %w", path, err))
	}
	encoded := base64.StdEncoding.EncodeToString(raw)
	if err := os.WriteFile(path, []byte(encoded), 0o600); err != nil {
		panic(fmt.Errorf("write %s: %w", path, err))
	}
}

func randomBytes(n int) []byte {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		panic(fmt.Errorf("read crypto/rand: %w", err))
	}
	return buf
}

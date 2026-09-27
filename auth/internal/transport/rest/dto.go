package rest

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}
type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type LoginResponse struct {
	AccessToken  string       `json:"accessToken"`
	RefreshToken string       `json:"refreshToken"`
	User         UserResponse `json:"user"`
}

type RegisterResponse struct {
	AccessToken  string       `json:"accessToken"`
	RefreshToken string       `json:"refreshToken"`
	User         UserResponse `json:"user"`
}
type RefreshResponse struct {
	RefreshToken string `json:"refreshToken"`
}
type RefreshRequest struct {
	RefreshToken string `json:"refreshToken"`
}
type UserResponse struct {
	UserID string `json:"userId"`
	Email  string `json:"email"`
}

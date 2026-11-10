package rest

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"net/http"
)

// PublicKeyHandler serves the RSA public key the service signs access tokens
// with. The Loregraph backend fetches it at startup and verifies tokens
// locally — no per-request round-trip here, no shared filesystem between the
// two services.
//
// No auth on purpose: the public key is, by definition, public. An attacker
// who has it can verify tokens but not forge them; that is the entire point
// of asymmetric signing.
type PublicKeyHandler struct {
	key *rsa.PublicKey
}

func NewPublicKeyHandler(key *rsa.PublicKey) *PublicKeyHandler {
	return &PublicKeyHandler{key: key}
}

func (h *PublicKeyHandler) Handle(w http.ResponseWriter, r *http.Request) {
	der, err := x509.MarshalPKIXPublicKey(h.key)
	if err != nil {
		http.Error(w, "cannot encode public key", http.StatusInternalServerError)
		return
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: der,
	})
	w.Header().Set("Content-Type", "application/x-pem-file")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(pemBytes)
}

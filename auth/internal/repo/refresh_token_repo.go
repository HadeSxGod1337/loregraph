package repo

import (
	"context"
	"loregraph_auth/internal/config"
	"loregraph_auth/internal/domain"
	"sort"
	"sync"
	"time"
)

type RefreshTokenRepo struct {
	mu     sync.RWMutex
	saveMu sync.Mutex

	tokens map[string]*domain.RefreshTokenModel
	path   string

	maxPerUser int
}

func NewRefreshTokenRepo(cfg config.RefreshTokenRepoConfig) *RefreshTokenRepo {
	r := &RefreshTokenRepo{
		tokens:     make(map[string]*domain.RefreshTokenModel),
		path:       cfg.Path,
		maxPerUser: cfg.MaxPerUser,
	}
	if err := r.load(); err != nil {
		panic(err)
	}
	return r
}

type refreshTokenFile struct {
	Tokens []*domain.RefreshTokenModel `json:"tokens"`
}

func (r *RefreshTokenRepo) load() error {
	var f refreshTokenFile
	if err := readJSON(r.path, &f); err != nil {
		return err
	}
	for _, t := range f.Tokens {
		if t != nil && t.HashedToken != "" {
			r.tokens[t.HashedToken] = t
		}
	}
	return nil
}

func (r *RefreshTokenRepo) save() error {
	r.saveMu.Lock()
	defer r.saveMu.Unlock()

	r.mu.RLock()
	snapshot := make([]*domain.RefreshTokenModel, 0, len(r.tokens))
	for _, t := range r.tokens {
		snapshot = append(snapshot, t)
	}
	r.mu.RUnlock()

	return atomicWriteJSON(r.path, refreshTokenFile{Tokens: snapshot})
}

func (r *RefreshTokenRepo) Create(ctx context.Context, token *domain.RefreshTokenModel) error {
	r.mu.Lock()
	r.cleanupLocked(token.UserID)
	// Room for the token we are about to insert: trim before insert, so a
	// max of N really means N stored, not N+1.
	r.trimLocked(token.UserID)
	r.tokens[token.HashedToken] = token
	r.mu.Unlock()

	return r.save()
}

func (r *RefreshTokenRepo) Get(ctx context.Context, hashedToken string) (*domain.RefreshTokenModel, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	t, ok := r.tokens[hashedToken]
	if !ok {
		return nil, domain.ErrTokenNotFound
	}
	return t, nil
}

func (r *RefreshTokenRepo) Revoke(ctx context.Context, hashedToken string) error {
	r.mu.Lock()
	t, ok := r.tokens[hashedToken]
	if !ok {
		r.mu.Unlock()
		return domain.ErrTokenNotFound
	}
	now := time.Now()
	t.RevokedAt = &now
	r.mu.Unlock()

	return r.save()
}

func (r *RefreshTokenRepo) RevokeAll(ctx context.Context, userID string) error {
	r.mu.Lock()
	now := time.Now()
	changed := false
	for _, t := range r.tokens {
		if t.UserID == userID && t.RevokedAt == nil {
			t.RevokedAt = &now
			changed = true
		}
	}
	r.mu.Unlock()

	if !changed {
		return nil
	}
	return r.save()
}

func (r *RefreshTokenRepo) cleanupLocked(userID string) {
	now := time.Now()
	for h, t := range r.tokens {
		if t.UserID != userID {
			continue
		}
		if t.RevokedAt != nil || t.ExpiresAt.Before(now) {
			delete(r.tokens, h)
		}
	}
}

// trimLocked evicts the oldest live tokens for a user so that adding one more
// does not push the count past maxPerUser. Called under the write lock, from
// Create, so it sees the same map Create is about to write into.
//
// The oldest go first: the newest token is the one the user just received and
// is most likely to still be using, and any older one is a leftover session
// that is either idle or about to expire anyway.
func (r *RefreshTokenRepo) trimLocked(userID string) {
	if r.maxPerUser <= 0 {
		return
	}

	type entry struct {
		hash    string
		created time.Time
	}
	var owned []entry
	for h, t := range r.tokens {
		if t.UserID == userID {
			owned = append(owned, entry{hash: h, created: t.CreatedAt})
		}
	}

	// Create is about to add one, so leave room for it.
	excess := len(owned) - r.maxPerUser + 1
	if excess <= 0 {
		return
	}

	sort.Slice(owned, func(i, j int) bool {
		return owned[i].created.Before(owned[j].created)
	})
	for i := 0; i < excess; i++ {
		delete(r.tokens, owned[i].hash)
	}
}

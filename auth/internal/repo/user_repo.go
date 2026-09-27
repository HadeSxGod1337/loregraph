package repo

import (
	"context"
	"sort"
	"sync"

	"loregraph_auth/internal/config"
	"loregraph_auth/internal/domain"
)

// UserRepo keeps users in memory, backed by a single JSON file.
//
// Two maps, not one, because lookups happen on different axes: FindByEmail
// on the login path, FindRoleByUserID on refresh. users_auth is the source
// of truth for both — the User struct carries the role inline and that is
// the copy a human edits by hand when bootstrapping without the admin UI.
// users_role is a derived index, rebuilt from users_auth on load; the two
// must never disagree, or "log in as master, get a master token, then
// refresh into a user token" becomes possible (see load()).
type UserRepo struct {
	muAuth sync.RWMutex
	muRole sync.RWMutex
	saveMu sync.Mutex

	usersAuth map[string]*domain.User
	usersRole map[string]string

	path string
}

func NewUserRepo(cfg config.UserRepoConfig) *UserRepo {
	r := &UserRepo{
		usersAuth: make(map[string]*domain.User),
		usersRole: make(map[string]string),
		path:      cfg.Path,
	}
	if err := r.load(); err != nil {
		panic(err)
	}
	return r
}

type userRepoFile struct {
	UsersAuth map[string]*domain.User `json:"users_auth"`
	UsersRole map[string]string       `json:"users_role"`
}

func (r *UserRepo) load() error {
	var f userRepoFile
	if err := readJSON(r.path, &f); err != nil {
		return err
	}
	for k, v := range f.UsersAuth {
		r.usersAuth[k] = v
	}
	// Rebuild the role index from users_auth. Whatever the file's own
	// users_role map contained is deliberately discarded: the same value
	// already lives in users_auth, and if the two disagreed (hand edit, an
	// older format, someone flipping only one of the two by accident) the
	// one that sits next to the rest of the user data wins.
	r.usersRole = make(map[string]string, len(r.usersAuth))
	for _, user := range r.usersAuth {
		if user != nil && user.ID != "" {
			r.usersRole[user.ID] = user.Role
		}
	}
	return nil
}

func (r *UserRepo) save() error {
	r.saveMu.Lock()
	defer r.saveMu.Unlock()

	r.muAuth.RLock()
	defer r.muAuth.RUnlock()
	r.muRole.RLock()
	defer r.muRole.RUnlock()

	auth := make(map[string]*domain.User, len(r.usersAuth))
	for k, v := range r.usersAuth {
		auth[k] = v
	}
	role := make(map[string]string, len(r.usersRole))
	for k, v := range r.usersRole {
		role[k] = v
	}

	return atomicWriteJSON(r.path, userRepoFile{UsersAuth: auth, UsersRole: role})
}

func (r *UserRepo) Create(ctx context.Context, u *domain.User) error {
	r.muAuth.Lock()
	r.usersAuth[u.Email] = u
	r.muAuth.Unlock()

	r.muRole.Lock()
	r.usersRole[u.ID] = u.Role
	r.muRole.Unlock()

	return r.save()
}

func (r *UserRepo) FindByEmail(ctx context.Context, email string) (*domain.User, error) {
	r.muAuth.RLock()
	defer r.muAuth.RUnlock()

	u, ok := r.usersAuth[email]
	if !ok {
		return nil, domain.ErrUserNotFound
	}
	return u, nil
}

// FindByID is a linear scan, not a lookup: users_auth is keyed by email, and
// the admin UI needs to reach a user by the ID the JWT carries. The map is
// small by construction (AUTH_MAX_USERS caps it at ten by default), so the
// scan is cheaper than a second index that would have to be kept in sync on
// every write.
func (r *UserRepo) FindByID(ctx context.Context, id string) (*domain.User, error) {
	r.muAuth.RLock()
	defer r.muAuth.RUnlock()

	for _, u := range r.usersAuth {
		if u.ID == id {
			return u, nil
		}
	}
	return nil, domain.ErrUserNotFound
}

// ListAll returns every user, oldest first. Deterministic ordering matters
// for the admin UI: an unsorted map reshuffles the list between refreshes,
// and reordering rows under a click is how the wrong role gets toggled.
func (r *UserRepo) ListAll(ctx context.Context) ([]*domain.User, error) {
	r.muAuth.RLock()
	defer r.muAuth.RUnlock()

	users := make([]*domain.User, 0, len(r.usersAuth))
	for _, u := range r.usersAuth {
		users = append(users, u)
	}
	sort.Slice(users, func(i, j int) bool {
		return users[i].CreatedAt.Before(users[j].CreatedAt)
	})
	return users, nil
}

func (r *UserRepo) Update(ctx context.Context, u *domain.User) error {
	r.muAuth.Lock()
	r.usersAuth[u.Email] = u
	r.muAuth.Unlock()

	// Keep the role index in step: Update may have changed the role.
	r.muRole.Lock()
	r.usersRole[u.ID] = u.Role
	r.muRole.Unlock()

	return r.save()
}

func (r *UserRepo) FindRoleByUserID(ctx context.Context, userID string) (string, error) {
	r.muRole.RLock()
	defer r.muRole.RUnlock()

	role, ok := r.usersRole[userID]
	if !ok {
		return "", domain.ErrUserNotFound
	}
	return role, nil
}

// CreateRoleByID changes a user's role and keeps users_auth in the same
// call, so the two maps cannot drift. Returns ErrUserNotFound when no user
// has that ID — the admin endpoint distinguishes "no such user" (404) from
// "not allowed" (403).
func (r *UserRepo) CreateRoleByID(ctx context.Context, userID, role string) error {
	found := false
	r.muAuth.Lock()
	for _, u := range r.usersAuth {
		if u.ID == userID {
			u.Role = role
			found = true
			break
		}
	}
	r.muAuth.Unlock()

	if !found {
		return domain.ErrUserNotFound
	}

	r.muRole.Lock()
	r.usersRole[userID] = role
	r.muRole.Unlock()

	return r.save()
}

func (r *UserRepo) Count(ctx context.Context) (int, error) {
	r.muAuth.RLock()
	defer r.muAuth.RUnlock()
	return len(r.usersAuth), nil
}

// DeleteByID removes the user with the given id from both maps and returns
// the row that was removed. A missing id is ErrUserNotFound, same as
// FindByID — the admin endpoint maps that to 404 either way.
func (r *UserRepo) DeleteByID(ctx context.Context, id string) (*domain.User, error) {
	var removed *domain.User
	r.muAuth.Lock()
	for email, u := range r.usersAuth {
		if u.ID == id {
			removed = u
			delete(r.usersAuth, email)
			break
		}
	}
	r.muAuth.Unlock()

	if removed == nil {
		return nil, domain.ErrUserNotFound
	}

	r.muRole.Lock()
	delete(r.usersRole, id)
	r.muRole.Unlock()

	if err := r.save(); err != nil {
		return nil, err
	}
	return removed, nil
}

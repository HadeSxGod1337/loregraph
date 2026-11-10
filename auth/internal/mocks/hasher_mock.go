package mocks

import "github.com/stretchr/testify/mock"

type MockHasher struct {
	mock.Mock
}

func (m *MockHasher) Hash(testPassword string) (string, error) {
	args := m.Called(testPassword)
	return args.String(0), args.Error(1)
}
func (m *MockHasher) Verify(testPassword string, hash string) (bool, error) {
	args := m.Called(testPassword, hash)
	return args.Bool(0), args.Error(1)
}

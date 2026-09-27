package testutils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func AssertError(t *testing.T, err error, wantErr error, wantErrContains string) {
	if wantErr != nil {
		assert.ErrorIs(t, err, wantErr)
	}
	if wantErrContains != "" {
		assert.Error(t, err)
		assert.Contains(t, err.Error(), wantErrContains)
	}
	if wantErr == nil && wantErrContains == "" {
		assert.NoError(t, err)
	}
}

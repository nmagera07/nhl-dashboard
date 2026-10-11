import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { clearResponseCache } from '../utils/responseCache.js';

// The response cache lives for the session (like a browser tab); each test
// starts with a fresh one so cached data can't leak between tests.
afterEach(() => clearResponseCache());

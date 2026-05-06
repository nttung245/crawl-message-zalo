# Next.js + TypeScript Coding Standards

> Quy tắc code chuẩn — dễ maintain, dễ deploy, dễ teamwork  
> Áp dụng cho: Next.js 13+ (App Router), TypeScript, Deploy trên VPS công ty

---

## Mục lục

1. [Cấu trúc thư mục](#1-cấu-trúc-thư-mục)
2. [Naming Convention](#2-naming-convention)
3. [Components](#3-components)
4. [TypeScript](#4-typescript)
5. [State Management & Data Fetching](#5-state-management--data-fetching)
6. [Deploy trên VPS công ty](#6-deploy-trên-vps-công-ty)
7. [Checklist trước khi deploy](#7-checklist-trước-khi-deploy)

---

## 1. Cấu trúc thư mục

### Layout chuẩn (App Router)

```
src/
├── app/                        # App Router (Next.js 13+)
│   ├── (auth)/                 # Route group — không ảnh hưởng URL
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx
│   │   └── [id]/page.tsx       # Dynamic route
│   ├── api/                    # Route Handlers
│   │   └── users/route.ts
│   ├── error.tsx               # Error boundary toàn cục
│   ├── loading.tsx             # Loading state toàn cục
│   ├── not-found.tsx
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── ui/                     # Reusable atomic components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── index.ts            # Barrel export
│   ├── features/               # Feature-specific components
│   │   └── auth/
│   │       └── LoginForm.tsx
│   └── layouts/                # Layout components
│       └── Sidebar.tsx
├── hooks/                      # Custom hooks
│   └── useAuth.ts
├── lib/                        # Utilities, helpers
│   ├── utils.ts
│   ├── constants.ts
│   └── env.ts                  # Environment validation
├── services/                   # API calls, external services
│   └── userService.ts
├── store/                      # State management (Zustand)
│   └── useUserStore.ts
├── types/                      # Global TypeScript types
│   ├── index.ts
│   └── api.ts
└── styles/
    └── globals.css
```

### Barrel exports

Dùng `index.ts` để re-export, tránh import path dài.

```typescript
// components/ui/index.ts
export { Button } from './Button'
export { Input } from './Input'
export { Modal } from './Modal'

// Import ở nơi khác — gọn hơn nhiều
import { Button, Input } from '@/components/ui'
```

### Path alias — bắt buộc

```typescript
// ❌ Không nên
import { useAuth } from '../../../hooks/useAuth'

// ✅ Nên dùng
import { useAuth } from '@/hooks/useAuth'
```

Cấu hình trong `tsconfig.json`:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

---

## 2. Naming Convention

### Files & Folders

| Loại | Convention | Ví dụ |
|------|-----------|-------|
| Component file | PascalCase | `UserProfile.tsx` |
| Hook | camelCase, prefix `use` | `useUserProfile.ts` |
| Utility / Service | camelCase | `userService.ts`, `formatDate.ts` |
| Route folder | kebab-case | `user-profile/` |
| Constant | UPPER_SNAKE_CASE | `API_BASE_URL` |
| Type / Interface | PascalCase | `UserProfile`, `ApiResponse` |

### Variables & Functions

```typescript
// Variables — camelCase
const userName = 'Nam'
const isLoading = true
const hasPermission = false

// Constants — UPPER_SNAKE_CASE
const MAX_RETRIES = 3
const API_TIMEOUT_MS = 5000

// Functions — động từ + danh từ, rõ nghĩa
const fetchUserById = (id: string) => { ... }
const handleLoginSubmit = (data: LoginForm) => { ... }
const validateEmailFormat = (email: string): boolean => { ... }

// Event Handlers — pattern: handle + Element + Event
const handleButtonClick = () => { ... }
const handleFormSubmit = (e: FormEvent) => { ... }
const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => { ... }
```

### Component Props — prefix `on` cho callback

```typescript
interface UserCardProps {
  user: User
  onSelect: (id: string) => void   // ✅ prefix on
  onDelete?: (id: string) => void  // ✅ optional với ?
  className?: string
}
```

---

## 3. Components

### Cấu trúc chuẩn một component

```typescript
// 1. Imports — thứ tự: react → next → third-party → internal
import { useState, useCallback } from 'react'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import type { User } from '@/types'

// 2. Types / Interfaces
interface UserCardProps {
  user: User
  onSelect?: (id: string) => void
  className?: string
}

// 3. Component — arrow function, named export
export const UserCard = ({ user, onSelect, className }: UserCardProps) => {
  // 4. State & refs
  const [isExpanded, setIsExpanded] = useState(false)

  // 5. Derived state & memos
  const fullName = `${user.firstName} ${user.lastName}`

  // 6. Handlers
  const handleClick = useCallback(() => {
    onSelect?.(user.id)
  }, [user.id, onSelect])

  // 7. Effects (nếu có)

  // 8. Return JSX
  return (
    <div className={cn('card', className)} onClick={handleClick}>
      <span>{fullName}</span>
    </div>
  )
}

// 9. Default export (tùy chọn)
export default UserCard
```

### Server vs Client Component

```typescript
// Server Component — mặc định, KHÔNG có 'use client'
// Ưu tiên dùng để: fetch data, hiển thị static content
async function UsersPage() {
  const users = await fetchUsers() // fetch trực tiếp
  return <UserList users={users} />
}

// Client Component — thêm 'use client' khi CẦN
// Chỉ dùng khi: hooks, event listeners, browser APIs
'use client'
import { useState } from 'react'

export const Counter = () => {
  const [count, setCount] = useState(0)
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>
}
```

**Quy tắc:** Đẩy `'use client'` xuống thấp nhất có thể trong cây component.

### Component không quá 150 dòng

Tách logic phức tạp ra custom hook:

```typescript
// hooks/useUserForm.ts — logic ở đây
export const useUserForm = () => {
  const [values, setValues] = useState<UserFormData>({...})
  const [errors, setErrors] = useState<FormErrors>({})

  const handleSubmit = async (data: UserFormData) => { ... }
  const validate = (field: string, value: string) => { ... }

  return { values, errors, handleSubmit, validate }
}

// components/features/user/UserForm.tsx — chỉ render UI
export const UserForm = () => {
  const { values, errors, handleSubmit } = useUserForm()
  return <form onSubmit={handleSubmit}>...</form>
}
```

### Tránh prop drilling — dùng Context

```typescript
// ❌ Prop drilling
<Page user={user} onLogout={fn}>
  <Header user={user} onLogout={fn}>
    <Avatar user={user} />
  </Header>
</Page>

// ✅ Context
const UserContext = createContext<UserContextType | null>(null)

export const UserProvider = ({ user, children }: Props) => (
  <UserContext.Provider value={{ user }}>
    {children}
  </UserContext.Provider>
)

export const useUser = () => {
  const ctx = useContext(UserContext)
  if (!ctx) throw new Error('useUser must be used within UserProvider')
  return ctx
}
```

---

## 4. TypeScript

### Bật strict mode — bắt buộc

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true
  }
}
```

### Không dùng `any` — dùng `unknown` hoặc type cụ thể

```typescript
// ❌ Sai
const data: any = fetchData()
function process(input: any) {}

// ✅ Đúng
const data: User = await fetchData()
function process(input: unknown) {
  if (typeof input === 'string') {
    // TypeScript biết input là string trong block này
  }
}
```

### Type vs Interface

```typescript
// Interface — dùng cho objects, có thể extend
interface User {
  id: string
  email: string
  createdAt: Date
}

interface AdminUser extends User {
  role: 'admin'
  permissions: string[]
}

// Type — dùng cho unions, primitives, utilities
type Status = 'idle' | 'loading' | 'success' | 'error'
type UserId = string
type PartialUser = Partial<User>
type CreateUser = Omit<User, 'id' | 'createdAt'>
type UpdateUser = Partial<Pick<User, 'email' | 'name'>>
```

### Utility Types hay dùng

```typescript
Partial<T>       // Tất cả fields optional
Required<T>      // Tất cả fields required
Readonly<T>      // Không thể mutate
Pick<T, K>       // Chọn một số fields
Omit<T, K>       // Loại bỏ một số fields
Record<K, V>     // Object với key K và value V
NonNullable<T>   // Loại bỏ null | undefined
ReturnType<F>    // Type trả về của function
```

### Generic API Response

```typescript
interface ApiResponse<T> {
  data: T
  message: string
  success: boolean
  pagination?: {
    page: number
    limit: number
    total: number
  }
}

type UsersResponse = ApiResponse<User[]>
type UserResponse = ApiResponse<User>
```

### Zod — validate + infer type (nên dùng)

```typescript
import { z } from 'zod'

// Định nghĩa schema một lần
const UserSchema = z.object({
  email: z.string().email('Email không hợp lệ'),
  name: z.string().min(2).max(50),
  age: z.number().min(0).max(120).optional(),
})

// TypeScript type tự động infer từ schema
type User = z.infer<typeof UserSchema>

// Validate khi nhận data từ bên ngoài
const result = UserSchema.safeParse(formData)
if (!result.success) {
  console.error(result.error.flatten())
  return
}
const user = result.data // type-safe User
```

---

## 5. State Management & Data Fetching

### Chọn đúng tool

| Loại state | Tool |
|-----------|------|
| UI state (modal, tab, toggle) | `useState` |
| Form state | `react-hook-form` |
| Server / async data | TanStack Query (React Query) |
| Global client state | Zustand |
| URL / filter state | `useSearchParams` (Next.js) |
| Complex global state | Redux Toolkit (chỉ khi thực sự cần) |

### Data fetching trong App Router

```typescript
// ✅ Server Component — fetch trực tiếp, tận dụng cache Next.js
async function UsersPage() {
  const users = await fetch(`${process.env.API_URL}/users`, {
    next: { revalidate: 60 }, // Revalidate sau 60 giây
    // cache: 'no-store'       // Không cache — dùng cho real-time data
  }).then(r => r.json())

  return <UserList users={users} />
}

// ✅ Client Component — dùng React Query
'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const { data, isLoading, error } = useQuery({
  queryKey: ['users'],
  queryFn: () => userService.getAll(),
  staleTime: 1000 * 60, // 1 phút
})

const queryClient = useQueryClient()
const mutation = useMutation({
  mutationFn: userService.create,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['users'] })
  },
})
```

### Services layer — tách API call

```typescript
// services/userService.ts
const BASE = process.env.NEXT_PUBLIC_API_URL

export const userService = {
  getAll: (): Promise<User[]> =>
    fetch(`${BASE}/users`).then(handleResponse),

  getById: (id: string): Promise<User> =>
    fetch(`${BASE}/users/${id}`).then(handleResponse),

  create: (data: CreateUser): Promise<User> =>
    fetch(`${BASE}/users`, {
      method: 'POST',
      body: JSON.stringify(data),
      headers: { 'Content-Type': 'application/json' },
    }).then(handleResponse),

  update: (id: string, data: UpdateUser): Promise<User> =>
    fetch(`${BASE}/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
      headers: { 'Content-Type': 'application/json' },
    }).then(handleResponse),

  delete: (id: string): Promise<void> =>
    fetch(`${BASE}/users/${id}`, { method: 'DELETE' }).then(handleResponse),
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const error = await res.json().catch(() => ({ message: res.statusText }))
    throw new Error(error.message || 'Request failed')
  }
  return res.json()
}
```

### Error Handling

```typescript
// app/users/error.tsx — Error boundary cho route
'use client'

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div>
      <h2>Đã có lỗi xảy ra</h2>
      <p>{error.message}</p>
      <button onClick={reset}>Thử lại</button>
    </div>
  )
}

// app/users/loading.tsx — Loading state
export default function Loading() {
  return <div>Đang tải...</div>
}
```

---

## 6. Deploy trên VPS công ty

### Cấu trúc thư mục trên VPS

```
/var/www/
└── myapp/
    ├── current/          # Symlink → release hiện tại
    ├── releases/
    │   ├── 20240101/
    │   └── 20240115/     # Mỗi lần deploy là một folder mới
    └── shared/
        ├── .env.local    # File env — KHÔNG đưa vào git
        └── logs/
```

### Environment Variables

```bash
# .env.local trên VPS — không bao giờ commit lên git
# Tạo thủ công trên server lần đầu, cập nhật thủ công khi cần

DATABASE_URL=postgresql://user:password@localhost:5432/myapp
JWT_SECRET=your-super-secret-key-minimum-32-chars
NEXTAUTH_SECRET=another-secret-key

# NEXT_PUBLIC_ — accessible ở client-side
NEXT_PUBLIC_API_URL=https://api.mycompany.com
NEXT_PUBLIC_APP_NAME=My App
```

Validate env khi khởi động app:

```typescript
// lib/env.ts
import { z } from 'zod'

const envSchema = z.object({
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  NEXT_PUBLIC_API_URL: z.string().url(),
  NODE_ENV: z.enum(['development', 'test', 'production']),
})

export const env = envSchema.parse(process.env)
// App sẽ crash ngay khi khởi động nếu env thiếu/sai — tốt hơn crash lúc runtime
```

### next.config.ts

```typescript
import type { NextConfig } from 'next'

const config: NextConfig = {
  reactStrictMode: true,

  // Tối ưu output — tạo standalone build để deploy dễ hơn
  output: 'standalone',

  // Cấu hình domain ảnh
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'cdn.mycompany.com' },
      { protocol: 'https', hostname: 'assets.mycompany.com' },
    ],
  },

  // Security headers
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=()' },
        ],
      },
    ]
  },
}

export default config
```

### package.json scripts

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "type-check": "tsc --noEmit",
    "check": "npm run type-check && npm run lint",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

### Process Manager — PM2

Cài đặt và cấu hình PM2 trên VPS:

```bash
# Cài PM2 global
npm install -g pm2

# Tạo file ecosystem.config.js trong project
```

```javascript
// ecosystem.config.js
module.exports = {
  apps: [
    {
      name: 'myapp',
      script: 'node_modules/.bin/next',
      args: 'start',
      cwd: '/var/www/myapp/current',
      instances: 'max',         // Dùng tất cả CPU cores
      exec_mode: 'cluster',
      env: {
        NODE_ENV: 'production',
        PORT: 3000,
      },
      // Tự restart nếu memory vượt 512MB
      max_memory_restart: '512M',
      // Log
      error_file: '/var/www/myapp/shared/logs/err.log',
      out_file: '/var/www/myapp/shared/logs/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
}
```

```bash
# Khởi động app
pm2 start ecosystem.config.js

# Auto-start sau khi VPS reboot
pm2 startup
pm2 save

# Các lệnh hay dùng
pm2 status          # Xem trạng thái
pm2 logs myapp      # Xem logs
pm2 reload myapp    # Reload không downtime (zero-downtime)
pm2 restart myapp   # Restart có downtime
pm2 stop myapp      # Dừng app
```

### Nginx reverse proxy

```nginx
# /etc/nginx/sites-available/myapp.conf
server {
    listen 80;
    server_name myapp.mycompany.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name myapp.mycompany.com;

    ssl_certificate     /etc/ssl/certs/myapp.crt;
    ssl_certificate_key /etc/ssl/private/myapp.key;

    # Bảo mật SSL
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Static files — cache dài
    location /_next/static/ {
        proxy_pass http://localhost:3000;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # Public folder
    location /public/ {
        proxy_pass http://localhost:3000;
        add_header Cache-Control "public, max-age=86400";
    }

    # App
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeout
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

```bash
# Kiểm tra config Nginx
nginx -t

# Reload Nginx
systemctl reload nginx
```

### Deploy script

Tạo file `scripts/deploy.sh` trong project:

```bash
#!/bin/bash
set -e  # Dừng nếu có lỗi

echo "=== Bắt đầu deploy ==="

APP_DIR="/var/www/myapp"
RELEASE_DIR="$APP_DIR/releases/$(date +%Y%m%d_%H%M%S)"
CURRENT_DIR="$APP_DIR/current"
SHARED_DIR="$APP_DIR/shared"

# 1. Tạo thư mục release mới
mkdir -p "$RELEASE_DIR"

# 2. Copy code mới lên (từ CI hoặc git pull)
git -C "$RELEASE_DIR" clone https://github.com/mycompany/myapp.git . --depth=1

# 3. Symlink file env từ shared
ln -s "$SHARED_DIR/.env.local" "$RELEASE_DIR/.env.local"

# 4. Cài dependencies
cd "$RELEASE_DIR"
npm ci --production=false

# 5. Build
npm run build

# 6. Chuyển symlink current sang release mới
ln -sfn "$RELEASE_DIR" "$CURRENT_DIR"

# 7. Reload app — zero downtime
pm2 reload myapp

# 8. Dọn dẹp releases cũ (giữ lại 5 bản gần nhất)
ls -dt "$APP_DIR/releases"/* | tail -n +6 | xargs rm -rf

echo "=== Deploy hoàn thành! ==="
```

```bash
# Cấp quyền chạy
chmod +x scripts/deploy.sh
```

### GitHub Actions CI/CD (nếu dùng GitHub)

```yaml
# .github/workflows/deploy.yml
name: Deploy to VPS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install & Type Check & Lint
        run: |
          npm ci
          npm run type-check
          npm run lint

      - name: Build
        run: npm run build

      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /var/www/myapp
            git pull origin main
            npm ci
            npm run build
            pm2 reload myapp
```

Thêm các secrets trong GitHub → Settings → Secrets:
- `VPS_HOST`: IP hoặc domain của VPS
- `VPS_USER`: username SSH (thường là `deploy` hoặc `ubuntu`)
- `VPS_SSH_KEY`: private key SSH

### Monitoring & Logs

```bash
# Xem logs realtime
pm2 logs myapp --lines 100

# Xem logs lỗi
pm2 logs myapp --err

# Monitor CPU/Memory
pm2 monit

# Xem logs Nginx
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Kiểm tra app đang chạy
curl -I https://myapp.mycompany.com
```

### Rollback khi có sự cố

```bash
# Xem các bản release hiện có
ls -la /var/www/myapp/releases/

# Rollback về bản trước
ln -sfn /var/www/myapp/releases/20240101_120000 /var/www/myapp/current
pm2 reload myapp

echo "Rollback hoàn thành"
```

---

## 7. Checklist trước khi deploy

### Code Quality

- [ ] `npm run type-check` — không có TypeScript error
- [ ] `npm run lint` — không có ESLint warning/error
- [ ] `npm run test` — tất cả tests pass
- [ ] `npm run build` — build thành công ở local

### Cấu hình

- [ ] `.env.local` đã được cập nhật trên VPS với đúng giá trị production
- [ ] `NEXT_PUBLIC_API_URL` trỏ đúng server production
- [ ] `next.config.ts` đã thêm đúng domain vào `remotePatterns` nếu có ảnh mới
- [ ] `output: 'standalone'` đã bật trong `next.config.ts`

### Security

- [ ] Không có API key, secret, hay credential nào trong source code
- [ ] `.env*` đã có trong `.gitignore`
- [ ] Security headers đã cấu hình trong Nginx hoặc `next.config.ts`
- [ ] HTTPS đã bật, HTTP redirect sang HTTPS

### Performance

- [ ] Images dùng `next/image` — không dùng `<img>` thuần
- [ ] Dynamic import cho các component nặng
- [ ] Kiểm tra bundle size trong output `next build`

### VPS / Server

- [ ] PM2 đang chạy: `pm2 status`
- [ ] Nginx config hợp lệ: `nginx -t`
- [ ] Disk space còn đủ: `df -h`
- [ ] RAM còn đủ: `free -h`
- [ ] SSL certificate còn hạn: `certbot certificates`
- [ ] Đã backup database (nếu có migration)

### Sau khi deploy

- [ ] Truy cập URL production, kiểm tra app hoạt động
- [ ] Kiểm tra logs không có lỗi: `pm2 logs myapp --lines 50`
- [ ] Kiểm tra các tính năng quan trọng hoạt động đúng
- [ ] Theo dõi memory/CPU 5-10 phút đầu: `pm2 monit`

---

## Pre-commit hooks (nên cài đặt)

```bash
# Cài husky + lint-staged
npm install -D husky lint-staged

# Khởi tạo husky
npx husky init
```

```bash
# .husky/pre-commit
npm run type-check
npx lint-staged
```

```javascript
// lint-staged.config.js
export default {
  '*.{ts,tsx}': ['eslint --fix', 'prettier --write'],
  '*.{json,css,md}': ['prettier --write'],
}
```

---

*Cập nhật lần cuối: 2025 — Next.js 15, TypeScript 5, Node.js 20 LTS*

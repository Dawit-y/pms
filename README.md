# PMS API - Project Management System

Enterprise-level RESTful API for comprehensive project management, built with Django 6 and Django REST Framework.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django 6.0](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)

## Overview

PMS API is a robust, scalable project management system designed for enterprise environments. It provides comprehensive APIs for managing projects, budgets, users, and project data with enterprise-grade security, authentication, and monitoring capabilities.

## Key Features

### Core Functionality
- **Project Management**: Complete project lifecycle management with hierarchical structure support
- **Budget Management**: Budget requests, approvals, and tracking
- **User Management**: Role-based access control with JWT authentication
- **Project Data**: Structured data management for project-related information
- **Lookups**: Centralized reference data management

### Enterprise Features
- **API Versioning**: URL-based versioning (`/api/v1/`)
- **Rate Limiting**: Multi-tier throttling (anonymous, authenticated, burst, sustained)
- **Security Headers**: HSTS, CSP, Permissions-Policy, X-Frame-Options
- **JWT Authentication**: Token-based auth with refresh token rotation
- **Audit Logging**: Complete history tracking with django-simple-history
- **CORS Support**: Configurable cross-origin resource sharing
- **API Documentation**: Interactive Swagger UI and ReDoc

### Technical Highlights
- **Django 6.0.3**: Latest Django with built-in async support
- **PostgreSQL 18**: Advanced relational database
- **Redis**: Caching and session storage
- **Gunicorn**: Production WSGI server
- **Nginx**: Reverse proxy and static/media file serving
- **Systemd**: Service management and auto-restart

## Architecture

### Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│  (Web Apps, Mobile Apps, Third-party Integrations)          │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (Reverse Proxy)                     │
│         SSL/TLS Termination, Static/Media Files              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  Django Application Layer                    │
│                    (Gunicorn WSGI Server)                    │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Accounts   │  │   Projects   │  │    Budget    │      │
│  │   (Users)    │  │  (Projects)  │  │  (Budgets)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Project Data │  │   Lookups    │  │     Core     │      │
│  │   (Data)     │  │ (Reference)  │  │  (Shared)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  Middleware: Security, CORS, Throttling, Audit Logging       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│                                                               │
│  ┌──────────────────┐              ┌──────────────────┐     │
│  │   PostgreSQL 18  │              │     Redis 7.2    │     │
│  │  (Primary DB)    │              │  (Cache/Session) │     │
│  └──────────────────┘              └──────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Application Structure

```
pms_api/
├── pms_api/                    # Main application package
│   ├── accounts/               # User management & authentication
│   │   ├── models.py          # User model with soft delete
│   │   ├── serializers.py     # User & auth serializers
│   │   ├── views.py           # Auth endpoints (login, register, etc.)
│   │   └── tests/             # Comprehensive test suite
│   │
│   ├── projects/              # Project management
│   │   ├── models.py          # Project model with hierarchy
│   │   ├── serializers.py     # Project CRUD serializers
│   │   ├── views.py           # Project endpoints
│   │   └── tests/             # Project tests
│   │
│   ├── budget/                # Budget management
│   │   ├── models.py          # Budget request model
│   │   ├── serializers.py     # Budget serializers
│   │   ├── views.py           # Budget endpoints
│   │   └── tests/             # Budget tests
│   │
│   ├── project_data/          # Project data management
│   │   ├── models.py          # Project data models
│   │   ├── serializers.py     # Data serializers
│   │   └── views.py           # Data endpoints
│   │
│   ├── lookups/               # Reference data
│   │   ├── models.py          # Lookup tables
│   │   ├── serializers.py     # Lookup serializers
│   │   └── views.py           # Lookup endpoints
│   │
│   └── core/                  # Shared utilities
│       ├── middleware.py      # Custom middleware (access logging)
│       ├── pagination.py      # Standard pagination
│       ├── exceptions.py      # Custom exception handlers
│       ├── throttling.py      # Rate limiting classes
│       └── management/        # Management commands
│
├── config/                    # Django configuration
│   ├── settings/
│   │   ├── base.py           # Base settings
│   │   ├── local.py          # Local development
│   │   ├── production.py     # Production settings
│   │   └── test.py           # Test settings
│   ├── urls.py               # URL routing
│   └── api_router.py         # API endpoint registration
│
├── compose/                   # Docker configurations (optional)
│   ├── local/                # Local development
│   │   └── django/
│   └── production/           # Production deployment
│       ├── django/
│       ├── postgres/
│       └── nginx/
│
├── tests/                     # Integration tests
├── .envs/                     # Environment configurations
│   ├── .local/               # Local environment
│   └── .production/          # Production environment
│
└── docs/                      # Documentation
```

## API Endpoints

### Authentication (`/api/v1/auth/`)
- `POST /register/` - User registration
- `POST /login/` - User login (JWT tokens)
- `POST /logout/` - User logout
- `POST /token/refresh/` - Refresh access token
- `POST /password/change/` - Change password
- `POST /password/reset/` - Request password reset
- `POST /password/reset/confirm/` - Confirm password reset

### Users (`/api/v1/users/`)
- `GET /` - List users (paginated)
- `POST /` - Create user
- `GET /{id}/` - Retrieve user
- `PUT /{id}/` - Update user
- `PATCH /{id}/` - Partial update
- `DELETE /{id}/` - Soft delete user

### Projects (`/api/v1/projects/`)
- `GET /` - List projects (paginated, filtered)
- `POST /` - Create project
- `GET /{id}/` - Retrieve project
- `PUT /{id}/` - Update project
- `PATCH /{id}/` - Partial update
- `DELETE /{id}/` - Delete project

### Budget (`/api/v1/budget/`)
- `GET /` - List budget requests
- `POST /` - Create budget request
- `GET /{id}/` - Retrieve budget request
- `PUT /{id}/` - Update budget request
- `PATCH /{id}/` - Partial update
- `DELETE /{id}/` - Delete budget request

### Lookups (`/api/v1/lookups/`)
- Reference data endpoints for various lookup tables

### Documentation
- `GET /api/v1/docs/` - Swagger UI
- `GET /api/v1/redoc/` - ReDoc
- `GET /api/v1/schema/` - OpenAPI schema (JSON)

## Security Features

### Authentication & Authorization
- **JWT Tokens**: Access tokens (15 min) + Refresh tokens (7 days)
- **Token Rotation**: Automatic refresh token rotation
- **Token Blacklisting**: Revoked tokens are blacklisted
- **Password Hashing**: Argon2 (most secure)

### Rate Limiting
- **Anonymous**: 100 requests/hour
- **Authenticated**: 1,000 requests/hour
- **Burst Protection**: 60 requests/minute
- **Daily Limit**: 10,000 requests/day
- **Auth Endpoints**: 5 attempts/minute
- **Password Reset**: 3 attempts/hour
- **Admin Users**: 2,000 requests/hour

### Security Headers
- **HSTS**: HTTP Strict Transport Security
- **CSP**: Content Security Policy (temporarily disabled)
- **X-Frame-Options**: Clickjacking protection
- **X-Content-Type-Options**: MIME sniffing protection
- **Referrer-Policy**: Referrer information control
- **Permissions-Policy**: Browser feature restrictions

### Additional Security
- **CORS**: Configurable cross-origin policies
- **CSRF Protection**: Cross-site request forgery protection
- **SQL Injection**: Protected by Django ORM
- **XSS Protection**: Template auto-escaping
- **Secure Cookies**: HTTPOnly, Secure, SameSite flags

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 18
- Redis 7.2 (optional for local)
- uv (Python package manager)

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd pms_api
   ```

2. **Install dependencies**:
   ```bash
   # Install uv if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Install project dependencies
   uv sync
   ```

3. **Configure environment**:
   ```bash
   # Copy and edit .env file
   cp .env.example .env
   # Update DATABASE_URL, DJANGO_SECRET_KEY, etc.
   ```

4. **Run migrations**:
   ```bash
   uv run python manage.py migrate
   ```

5. **Create superuser**:
   ```bash
   uv run python manage.py createsuperuser
   ```

6. **Run development server**:
   ```bash
   uv run python manage.py runserver
   ```

7. **Access the application**:
   - API: http://127.0.0.1:8000/api/v1/
   - Admin: http://127.0.0.1:8000/admin/
   - Docs: http://127.0.0.1:8000/api/v1/docs/

## Testing

### Run All Tests

```bash
# Run tests with pytest
uv run pytest

# Run with coverage
uv run pytest --cov=pms_api

# Run specific test file
uv run pytest pms_api/accounts/tests/test_auth_api.py
```

### Test Coverage

```bash
# Generate coverage report
uv run coverage run -m pytest
uv run coverage report
uv run coverage html

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Code Quality

```bash
# Linting with ruff
uv run ruff check .

# Format code
uv run ruff format .

# Type checking with mypy
uv run mypy pms_api
```

## Deployment

### Production Deployment Options

Choose the deployment method that fits your needs:

#### Traditional Deployment (Recommended)
- [TRADITIONAL_DEPLOYMENT_GUIDE.md](./TRADITIONAL_DEPLOYMENT_GUIDE.md) - Complete Nginx + Gunicorn deployment
  - **With Domain**: Let's Encrypt SSL (trusted, no warnings)
  - **With IP Only**: ZeroSSL for trusted SSL certificates (no browser warnings!)
  - **Quick Demo**: Self-signed SSL option included

#### IP-Based Quick Start (Demo/Testing)
- [IP_BASED_DEPLOYMENT_QUICKSTART.md](./IP_BASED_DEPLOYMENT_QUICKSTART.md) - Fast deployment using IP address
  - Get trusted SSL certificate for IP address (ZeroSSL)
  - No domain name required
  - Perfect for demos and testing
  - ~1.5 hours total setup time

#### Docker Deployment (Optional)
- [DOCKER_PRODUCTION_SETUP.md](./DOCKER_PRODUCTION_SETUP.md) - Production Docker setup
- [VPS_DEPLOYMENT_GUIDE.md](./VPS_DEPLOYMENT_GUIDE.md) - Complete VPS deployment with CI/CD

### Quick Production Deploy

```bash
# Build production images
docker compose -f docker-compose.production.yml build

# Start services
docker compose -f docker-compose.production.yml up -d

# Run migrations
docker compose -f docker-compose.production.yml exec django python manage.py migrate

# Create superuser
docker compose -f docker-compose.production.yml exec django python manage.py createsuperuser
```

## Configuration

### Environment Variables

See [ENVIRONMENT_VARIABLES_GUIDE.md](./ENVIRONMENT_VARIABLES_GUIDE.md) for complete reference.

**Key Variables**:
- `DJANGO_SECRET_KEY` - Django secret key (50+ chars)
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `DJANGO_ALLOWED_HOSTS` - Allowed hostnames
- `DJANGO_DEBUG` - Debug mode (False in production)
- `MAILGUN_API_KEY` - Email service API key
- `CORS_ALLOWED_ORIGINS` - CORS allowed origins

### Settings Modules

- `config.settings.local` - Local development
- `config.settings.production` - Production
- `config.settings.test` - Testing

Set via `DJANGO_SETTINGS_MODULE` environment variable.

## Documentation

### Available Documentation

- [TRADITIONAL_DEPLOYMENT_GUIDE.md](./TRADITIONAL_DEPLOYMENT_GUIDE.md) - Traditional Nginx + Gunicorn deployment
- [DOCKER_LOCAL_SETUP.md](./DOCKER_LOCAL_SETUP.md) - Local Docker development (optional)
- [DOCKER_PRODUCTION_SETUP.md](./DOCKER_PRODUCTION_SETUP.md) - Production Docker setup (optional)
- [VPS_DEPLOYMENT_GUIDE.md](./VPS_DEPLOYMENT_GUIDE.md) - VPS deployment with CI/CD (Docker-based)
- [ENVIRONMENT_VARIABLES_GUIDE.md](./ENVIRONMENT_VARIABLES_GUIDE.md) - Environment configuration
- [SECURITY.md](./SECURITY.md) - Security features and best practices
- [ENTERPRISE_SECURITY_SUMMARY.md](./ENTERPRISE_SECURITY_SUMMARY.md) - Security summary
- [DJANGO6_CSP_MIGRATION.md](./DJANGO6_CSP_MIGRATION.md) - CSP migration guide

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: `/api/v1/docs/`
- **ReDoc**: `/api/v1/redoc/`
- **OpenAPI Schema**: `/api/v1/schema/`

## Management Commands

### Custom Commands

```bash
# Check security configuration
uv run python manage.py check_security

# Create superuser
uv run python manage.py createsuperuser

# Collect static files
uv run python manage.py collectstatic

# Run migrations
uv run python manage.py migrate

# Create migrations
uv run python manage.py makemigrations
```

### Database Backups (Docker)

```bash
# Create backup
docker compose -f docker-compose.production.yml exec postgres backup

# List backups
docker compose -f docker-compose.production.yml exec postgres backups

# Restore backup
docker compose -f docker-compose.production.yml exec postgres restore <backup-file>
```

## Performance

### Optimization Features

- **Database Connection Pooling**: `CONN_MAX_AGE=60`
- **Redis Caching**: Session and data caching
- **Static File Compression**: Whitenoise with compression
- **Query Optimization**: Select/prefetch related
- **Pagination**: Efficient cursor-based pagination
- **Gunicorn Workers**: Multi-process WSGI server

### Monitoring

- **Access Logging**: Custom middleware logs all API requests
- **Error Tracking**: Email notifications for 500 errors
- **Health Checks**: Built-in Django system checks
- **Performance Metrics**: Django Debug Toolbar (development)

## Contributing

### Development Workflow

1. Create a feature branch
2. Make changes
3. Run tests: `uv run pytest`
4. Run linting: `uv run ruff check .`
5. Format code: `uv run ruff format .`
6. Commit changes
7. Push and create pull request

### Code Style

- **Linting**: Ruff
- **Formatting**: Ruff format
- **Type Hints**: mypy
- **Line Length**: 100 characters
- **Import Sorting**: Single-line imports

## Troubleshooting

### Common Issues

**Database Connection Error**:
```bash
# Check PostgreSQL is running
docker compose -f docker-compose.local.yml ps postgres

# Verify DATABASE_URL in .env
echo $DATABASE_URL
```

**Port Already in Use**:
```bash
# Change port in docker-compose.local.yml
ports:
  - '8001:8000'  # Use different host port
```

**Black Screen on API Docs**:
- Clear browser cache (Ctrl+Shift+R)
- Check CSP settings (currently disabled)
- Verify authentication (docs require login in production)

**Migration Errors**:
```bash
# Reset migrations (development only)
uv run python manage.py migrate --fake-initial
```

## License

Not open source - Proprietary

## Support

For issues and questions:
- Create an issue in the repository
- Contact: dawityimer52@gmail.com

## Acknowledgments

- Built with [Cookiecutter Django](https://github.com/cookiecutter/cookiecutter-django/)
- Powered by [Django](https://www.djangoproject.com/)
- API framework: [Django REST Framework](https://www.django-rest-framework.org/)
- Documentation: [drf-spectacular](https://drf-spectacular.readthedocs.io/)

---

**Version**: 1.0.0
**Last Updated**: 2026-04-30

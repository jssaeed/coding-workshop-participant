# Coding Workshop - Deployment Scripts

## Overview

This directory contains development and deployment scripts that can be used with local development and cloud deployment.

## Quick Start

### Local Development

To run your application locally:

```sh
./bin/start-dev.sh
```

### Cloud Deployment

To deploy your backend to AWS:

```sh
./bin/deploy-backend.sh
```

To deploy your frontend to AWS:

```sh
./bin/deploy-frontend.sh
```

### Testing

To run the backend test suites, smoke-test a running server, or load-test the cloud deployment:

```sh
./bin/test-backend.sh
./bin/smoke-test.sh "$(cd infra && terraform output -raw api_base_url)"
./bin/load-test.sh "$(cd infra && terraform output -raw api_base_url)" --profile smoke
```

## Available Scripts

### `deploy-backend.sh`

**The main deployment script** - deploys complete infrastructure including backend Lambda functions.

**What it does**:

* Creates VPC, security groups, and networking
* Deploys all Lambda functions with Function URLs
* Sets up S3 bucket for frontend hosting
* Creates CloudFront distribution with routing (AWS only)
* Sets up DocumentDB cluster
* Auto-detects environment (LocalStack vs AWS)
* Loads participant credentials for multi-participant workshops

**When to use**:

* Initial deployment
* After changing Lambda function code
* After adding new Lambda functions (auto-discovered!)
* After infrastructure changes

**Key feature**: Terraform only updates changed resources, so running this after Lambda code changes is fast (~5-10 seconds).

**Usage**:

```sh
./bin/deploy-backend.sh [aws|local]
```

### `deploy-frontend.sh`

Builds and deploys the React frontend to AWS.

**What it does**:

* LocalStack: Displays message to use `npm run dev` (skips S3 deployment)
* AWS:
  * Loads participant environment credentials
  * Runs `npm run build` to create production build
  * Uploads static files to S3 bucket
  * Invalidates CloudFront cache
  * Displays CloudFront URL

**When to use**:

* LocalStack: Don't use this - use `./bin/start-dev.sh` for hot-reload instead
* AWS only: After making changes to React components

**Why skip LocalStack S3?** The dev server (`npm run dev`) provides instant hot-reload (1-2 seconds) vs full build+deploy (~30-60 seconds).

**Usage**:

```sh
./bin/deploy-frontend.sh [aws|local]
```

### `start-dev.sh`

Starts the complete development environment with hot-reload.

**What it does**:

* Checks LocalStack is running
* Verifies backend is deployed
* Generates `.env.local` for frontend
* Starts proxy server on port 3001 (CORS workaround)
* Starts React dev server on port 3000 (hot-reload)

**When to use**:

* LocalStack development (recommended workflow)
* Frontend development with backend integration
* Testing full stack locally

**Usage**:

```sh
./bin/start-dev.sh
```

### `generate-env.sh`

Generates `.env.local` file for React frontend.

**What it does**:

* Detects LocalStack vs AWS environment
* Reads Terraform outputs (API URLs, endpoints)
* Generates frontend environment configuration
* LocalStack: Sets proxy URL (`http://localhost:3001`)
* AWS: Sets CloudFront URL

**When to use**:

* After deploying backend
* After adding new Lambda functions
* When switching between LocalStack and AWS

**Usage**:

```sh
./bin/generate-env.sh
```

### `proxy-server.js`

Development CORS proxy server for LocalStack.

**What it does**:

* Listens on port 3001
* Forwards `/api/*` requests to LocalStack Lambda URLs
* Strips browser headers that trigger LocalStack CORS bug
* Adds proper CORS headers to responses

**Why needed**: LocalStack Lambda Function URLs have a CORS bug.

**Usage** (automatically started by `start-dev.sh`):

```sh
node ./bin/proxy-server.js
```

### `setup-participant.sh`

**One-time setup for multi-participant AWS workshops** - configures participant credentials automatically.

**What it does**:

* Auto-detects AWS Account ID from your credentials
* Constructs IAM role ARN: `arn:aws:iam::{ACCOUNT}:role/coding-workshop-{PARTICIPANT_ID}`
* Constructs S3 backend bucket: `coding-workshop-tfstate-{PARTICIPANT_ID}`
* Creates AWS CLI profile: `coding-workshop-{PARTICIPANT_ID}`
* Generates Terraform backend config: `BACKEND.config`
* Creates environment file: `ENVIRONMENT.config` (auto-loaded by `deploy-backend.sh`)

**When to use**:

* Required: Before your first AWS deployment in multi-participant workshops
* Not needed: For LocalStack development (no participant isolation required)

**What you need**: Just 2 things from instructor:

1. Participant ID (e.g., `efgh5678`)
2. Participant Code (e.g., `xK9mP2nR4vT8wQ`)

Everything else (AWS Account ID, S3 bucket name, IAM role) is **automatically detected/derived**.

**Usage**:

```sh
# 1. First, set up environment variables
echo 'export EVENT_ID=your-id' >> ~/.bashrc
echo 'export PARTICIPANT_ID=your-id' >> ~/.bashrc
echo 'export PARTICIPANT_CODE=your-code' >> ~/.bashrc
source ~/.bashrc

# 2. Then, run the setup participant script
./bin/setup-participant.sh
```

### `setup-environment.sh`

Sets up the complete local development environment on Ubuntu 22.04.

**What it does**:

* Installs Docker (Container runtime)
* Installs LocalStack (AWS service emulation)
* Installs AWS CLI v2 (AWS command-line tools)
* Installs Terraform (Infrastructure as Code)
* Installs PostgreSQL (Relational database)
* Installs MongoDB (NoSQL database)
* Optionally: Installs and configures dnsmasq (DNS resolution)

**When to use**:

* Initial machine setup for Ubuntu 22.04
* First-time local development environment installation
* One-time per developer machine

**Prerequisites**:

* Ubuntu 22.04 Desktop
* Administrator/sudo access
* Internet connection for package downloads

**Usage**:

```sh
# Basic setup (without dnsmasq)
./bin/setup-environment.sh

# With dnsmasq DNS configuration
./bin/setup-environment.sh -d

# Dry run (show what would be done without making changes)
./bin/setup-environment.sh -n

# Both dnsmasq and dry run
./bin/setup-environment.sh -d -n
```

**Notes**:

* Script auto-detects if dependencies are already installed and skips redundant steps
* Continues on non-critical errors and reports all issues at the end
* Dry run mode (`-n`) shows planned actions without making changes
* dnsmasq (`-d`) is optional - enables DNS resolution for `.local` domains

### `test-backend.sh`

Runs every backend service's pytest suite (unit, integration and error-handling tests), one service at a time.

**What it does**:

* Runs `backend/_shared/tests` and each `backend/<service>/tests` with the backend virtualenv
* Integration tests use a separate PostgreSQL database, `incident_tracker_test`, created on first run
* Skips the integration tests (with a reason) when PostgreSQL is not running
* Writes JUnit XML, coverage XML and a summary to `test-results/backend/`

**When to use**:

* Before committing backend changes; no server or deploy needed

**Usage**:

```sh
./bin/test-backend.sh [--cov] [--unit] [service ...] [-- pytest args]
```

See [backend/TESTING.md](../backend/TESTING.md).

### `smoke-test.sh`

Runs the HTTP smoke tests in `backend/_e2e` against a running server, local or cloud.

**What it does**:

* Walks the main user journeys over plain HTTP: sign up, log in, file a ticket, comment, inbox, refresh, log out
* Creates throw-away `smoke-*@acme.inc` accounts and deletes them again with the db admin account
* Reports API responses that are not JSON, which is how a CloudFront error-page fallback shows up
* Writes JUnit XML to `test-results/smoke/<date>.xml`

**When to use**:

* After `./bin/start-dev.sh`, to check the local stack end to end
* After `./bin/deploy-backend.sh`, to check the deploy actually serves the API

**Usage**:

```sh
./bin/smoke-test.sh [base_url]     # default http://localhost:3001
./bin/smoke-test.sh "$(cd infra && terraform output -raw api_base_url)"
```

### `load-test.sh`

Runs the Artillery load test in `backend/_load/artillery.yml` against a server.

**What it does**:

* Fetches Artillery with `npx` (needs Node.js and network access on first use)
* Signs up a throw-away `loadtest-*@acme.inc` account and logs in once; every virtual user reuses that token
* Sends a mix that follows the frontend: inbox badge polling, ticket browsing, occasional ticket filing
* Fails when p95 latency exceeds 1.5 s, p99 exceeds 3 s, or more than 1% of requests error
* Writes a JSON report to `test-results/load/`

**When to use**:

* AWS only. Local Lambdas run as single Docker containers with no scaling, so local numbers mean nothing
* Start with `--profile smoke`; the account is shared, so ramp up only when that is clean

**Usage**:

```sh
./bin/load-test.sh <base_url> [--profile smoke|full|heavy] [--email x --password y]
```

### `cleanup-environment.sh`

Destroys all infrastructure resources created by the deployment scripts.

**What it does**:

* Removes all AWS/LocalStack resources (VPC, Lambda, S3, CloudFront, DocumentDB, etc.)
* Uses Terraform to cleanly destroy infrastructure
* Verifies Terraform is installed before proceeding

**When to use**:

* End of workshop to clean up resources
* Before redeploying from scratch
* To avoid unnecessary AWS charges
* When resetting the environment

**Warning**: This action **cannot be undone**. All data and resources will be permanently deleted.

**Prerequisites**:

* Terraform must be installed
* Valid AWS credentials configured (for AWS deployments)
* LocalStack running (for LocalStack deployments)

**Usage**:

```sh
./bin/cleanup-environment.sh
```

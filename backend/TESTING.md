# Testing

How the project is tested, how to run the tests, what they found, and what is not covered. Backend in-process suites first, then smoke and load tests against a running server, then the frontend. Written against the testing expectations in the [Full Stack Guide](../docs/full-stack.md#testing-expectations).

## What is tested

The guide asks for three kinds of backend tests. Each service has all three in its `tests/` folder.

| Kind | What it means here | Where |
| --- | --- | --- |
| Unit | A service's Lambda handler runs in isolation. The database is replaced by a fake that refuses to run SQL, and the model functions are stubbed, so the tests check routing, input validation, role checks and JSON shapes with no PostgreSQL at all. | `backend/<service>/tests/test_routing.py`, `test_controller_unit.py` (`test_handler_unit.py` for migrations) |
| Integration | The real handler against a real PostgreSQL database with the real schema. Every SQL statement, constraint, transaction and lock is exercised, and each test checks the rows the request left behind. | `backend/<service>/tests/test_api.py` |
| Error handling | Every documented error in [API.md](./API.md): 400 for each validation rule (with the exact message, so the frontend can show it next to the right field), 401 for missing/invalid/expired tokens, 403 for the wrong role, 404 for missing or hidden records, 405, 409, and the 500 safety net that hides internal details. Failing requests are also checked to have saved nothing. | throughout |

The shared library (`backend/_shared`) has its own suite, `backend/_shared/tests/`, covering request parsing, response shapes, the validators, floor and room labels, password hashing, JWT creation and checking, refresh tokens, role rules, and the commit/rollback rules of `database.py`. It also checks that every service's `lib/` folder is an exact copy of `_shared` (so a forgotten `bin/sync-shared.sh` fails the build).

Helpers shared by every suite live in `backend/_testing/`: Lambda event builders, the fake database, and the test-database fixtures and row factories.

## Running the tests

One-time setup (the backend virtualenv already has the runtime libraries):

```sh
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

Run everything:

```sh
./bin/test-backend.sh            # every suite
./bin/test-backend.sh --cov      # with a coverage report per service
./bin/test-backend.sh --unit     # unit tests only, no database needed
./bin/test-backend.sh users incidents -- -k login -x   # some services, extra pytest args
```

Each service is its own Lambda with its own top-level packages (`controllers`, `models`, `views`, `lib`), so the suites must run one service at a time, from that service's folder. That is what the script does. To run one by hand:

```sh
cd backend/incidents && ../.venv/bin/python -m pytest tests
```

### The test database

Integration tests need the PostgreSQL that `./bin/start-dev.sh` starts (localhost:5432, user `postgres`, password `postgres123`). They connect with the same `POSTGRES_*` variables the services use but always to a **separate database**, `incident_tracker_test`, which they create on first run and empty between tests. The local development data in the `postgres` database is never touched; the helpers refuse to run against it. Set `TEST_POSTGRES_NAME` to use a different name.

When PostgreSQL is not reachable the integration tests **skip** with a reason, and pytest's `-ra` summary lists them. The unit tests still run.

Tests use psycopg's pure Python implementation (`PSYCOPG_IMPL=python`), because each service vendors its own psycopg release and the virtualenv may carry a different C accelerator. The SQL, and therefore what is tested, is the same.

## Where results are stored

Every runner writes to `test-results/` at the project root (ignored by git; add it as a CI artifact to keep a history):

| Path | Written by | Contents |
| --- | --- | --- |
| `test-results/backend/<service>.xml` | `bin/test-backend.sh` | JUnit XML per service (also `_shared`) |
| `test-results/backend/coverage-<service>.xml` | `bin/test-backend.sh --cov` | Coverage XML per service |
| `test-results/backend/summary.txt` | `bin/test-backend.sh` | Outcome and counts per service, with the time of the run |
| `test-results/frontend/junit.xml` | `npm test` (from `frontend/`) | JUnit XML |
| `test-results/frontend/coverage/` | `npm run test:coverage` | HTML report, `coverage-summary.json` |
| `test-results/smoke/<date>.xml` | `bin/smoke-test.sh` | JUnit XML, one file per run, so runs against different servers are kept apart |
| `test-results/load/<date>-<profile>.json` | `bin/load-test.sh` | Artillery's full report, one file per run |

JUnit XML is what CI systems and IDEs read to show pass/fail per test. Coverage and load files are overwritten only when they carry no date in the name.

## Results

Last run on 2026-09-24 (`./bin/test-backend.sh`, see `test-results/backend/summary.txt`):

| Suite | Tests | Coverage of the suite's own code (earlier `--cov` run) |
| --- | ---: | ---: |
| `_shared` (the library) | 210 | 98% |
| `users` | 107 | 100% |
| `buildings` | 72 | 99% |
| `incidents` | 193 | 99% |
| `messages` | 43 | 100% |
| `inbox` | 39 | 100% |
| `migrations` | 23 | 85% |
| **Total** | **687** | |

One test fails at the moment: `incidents/tests/test_api.py::TestStats::test_overview_counts_the_last_n_days`, which predates the paging work and expects the overview without the `resolution` block that the engineer-statistics change added. Everything else passes.

The suites cover the two rules every write and every list now follows:

- **Every request that writes runs in one transaction.** The controller opens `with transaction():` around the permission check, the row lock and the writes, so a request that fails half-way saves nothing (the unit tests count commits and rollbacks on the fake connection; the integration tests check the rows). Races that slip past a check are caught by the database's own rules and turned into the same `409` (a duplicate email at signup, a duplicate building name).
- **Every list is one page from the database.** `GET /api/incidents` and `GET /api/users` take `page`/`limit`/`q`/`sort`/`order` and answer `{items, total, page, limit, pages}`; `GET /api/messages` walks a thread newest-first with a `before` cursor. Tests check that pages do not overlap, that a message posted mid-read does not shift the pages, and that the migration creates the indexes the page queries use.

Coverage is line and branch coverage of `function.py`, `controllers/`, `models/` and `views/` for a service, and of every file for `_shared`. The uncovered lines in `migrations/function.py` are the upgrade paths for databases created by earlier versions of the schema (see below). Against the guide's goals: backend components and API endpoints are above the 80% and 90% marks, and every documented validation and error case has a test.

The whole run takes about 15 seconds; the unit-only run about 7.

## Testing the server

Everything above runs the code in-process. Two more tools test a **running server**, local or cloud, over HTTP. Neither imports service code; they only know the URL, so they prove what a deploy actually serves.

### Smoke tests (`backend/_e2e`)

```sh
./bin/smoke-test.sh                                                  # http://localhost:3001
./bin/smoke-test.sh "$(cd infra && terraform output -raw api_base_url)"   # the cloud
```

Fourteen tests walk the main journeys with the `requests` library: sign up, log in, file a ticket, read and list it, a stranger gets 404, comment on it, inbox, buildings, statistics, the error shapes, refresh-token rotation, logout, and the db admin listing accounts. They create `smoke-*@acme.inc` accounts and delete them afterwards with the db admin account (`SMOKE_ADMIN_EMAIL` / `SMOKE_ADMIN_PASSWORD`, default `admin@admin.com` / `admin123`). The tickets those accounts filed stay, shown as "Deleted user", because the API keeps history on purpose.

Results on 2026-09-23:

| Target | Result |
| --- | --- |
| Local (`http://localhost:3001`) | 14 passed in 6 s (rerun 2026-09-24) |
| Cloud (`https://d2jasp0923nmob.cloudfront.net`) | 12 passed, 2 failed in 29 s. See the finding below. |

**Finding: CloudFront turns API 404s into the React app.** On the cloud, `GET /api/incidents/{id}` for a ticket you may not see, or one that does not exist, answers `200` with the HTML of `index.html` instead of `404 {"error": "Incident not found"}`. The `X-Cache: Error from cloudfront` header and `infra/cloudfront.tf` explain it: the `custom_error_response` that maps 404 to `/index.html` (needed so the React router can own deep links) applies to every path, including `/api/*`. Nothing leaks, since the stranger gets HTML rather than the ticket, but the frontend's `response.json()` fails on it and every documented API 404 is wrong in the cloud. The fix is in Terraform, not the services: keep the fallback for the app's origin only (for example, set the error document on the S3 website origin, or a CloudFront function that rewrites unknown non-`/api/` paths). The smoke test names this cause in its failure message so nobody has to rediscover it. The API cache behaviour itself uses the managed CachingDisabled policy, which the test confirmed: two users polling the same URL each get their own answer.

### Load tests (`backend/_load`)

```sh
./bin/load-test.sh "$(cd infra && terraform output -raw api_base_url)" --profile smoke   # 20 s, to check the setup
./bin/load-test.sh "$(cd infra && terraform output -raw api_base_url)"                   # full: ramp to 15 new users/s, hold 90 s
./bin/load-test.sh "$(cd infra && terraform output -raw api_base_url)" --profile heavy   # ramp to 40 new users/s, hold 120 s
```

Uses [Artillery](https://www.artillery.io), fetched with `npx` (Node.js is already installed; the first run downloads it). The scenario in `artillery.yml` follows what the frontend does: the inbox badge poll is half the traffic, ticket browsing a third, ticket filing with a comment and the statistics page the rest. It signs up a throw-away `loadtest-*@acme.inc` account and logs in once, before the test, and every virtual user reuses that token. Login is kept out of the scenarios on purpose: bcrypt costs a quarter second of CPU per call by design, so a login-heavy test measures bcrypt, not the API. The run fails when p95 latency is over 1.5 s, p99 over 3 s, or more than 1% of requests fail to complete; every response is also checked for the expected status code. The JSON report lands in `test-results/load/`.

Run it against the **cloud**. Locally each Lambda is one LocalStack Docker container with no scaling: a full-profile run against `localhost:3001` produced socket timeouts, 500s and 502s with a p95 of 14 s, which says nothing about production. It also leaves the local stack slow for several minutes afterwards (LocalStack keeps the extra Lambda containers around), so run the local smoke test before any local load run, or restart `./bin/start-dev.sh` after one. The tickets the load test files stay in the database (the load-test user can be deleted from the Employee directory; the seed endpoint replaces everything).

Results on 2026-09-23, full profile against the cloud, all checks passed:

| | |
| --- | --- |
| Requests | 3605 in 167 s, 21 per second |
| Virtual users | 1890 created, 1890 completed, 0 failed |
| Status codes | 3259 x 200, 346 x 201, no errors, no timeouts |
| Latency, all requests | median 31 ms, p95 69 ms, p99 133 ms, max 2.5 s |

Per endpoint (milliseconds):

| Endpoint | median | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| GET /api/inbox/count | 26 | 52 | 133 | 2474 |
| GET /api/incidents | 32 | 74 | 116 | 824 |
| GET /api/incidents?status=open | 37 | 78 | 128 | 861 |
| GET /api/incidents/{id} | 35 | 56 | 125 | 780 |
| GET /api/messages?incidentId | 37 | 67 | 125 | 2357 |
| GET /api/buildings | 31 | 54 | 91 | 1086 |
| GET /api/incidents/stats/mine | 25 | 45 | 65 | 132 |
| POST /api/incidents | 29 | 54 | 82 | 771 |
| POST /api/messages | 35 | 73 | 105 | 738 |

The maximums are Lambda cold starts at the start of each phase: a new container opens its own PostgreSQL connection, which is what the 1 to 2.5 s outliers are. Everything after that is a few tens of milliseconds, so at this load neither Lambda concurrency nor Aurora connections are anywhere near a limit. The next step up is the `heavy` profile while watching CloudWatch (Lambda `Duration`, `Throttles`, `ConcurrentExecutions`; Aurora `DatabaseConnections`), since each Lambda container holds one database connection and a burst of new containers is the most likely place a serverless app runs out of something.

## Frontend tests (`frontend/tests`)

Vitest with React Testing Library in a jsdom browser, mirroring `src/`. Run from `frontend/`:

```sh
npm test                 # once
npm run test:coverage    # with a coverage report
```

| Kind (from the guide) | What it means here | Where |
| --- | --- | --- |
| Component tests | Every component and page rendered with React Testing Library and driven through the DOM: forms filled, dropdowns chosen, buttons clicked, and the result checked by what a user would see. Pages get `src/services/api.js` mocked, so a test states what the backend answers and checks what the page shows and sends. Every role's view is covered (employee, engineer, facility admin, db admin), as are loading, empty, success and error states. | `tests/components/`, `tests/pages/`, `tests/App.test.jsx` |
| API integration tests | `api.js` against a mocked `fetch`: URLs and query strings, the bearer header, JSON bodies, 204 handling, error messages with status, and the expired-token path (one refresh shared by concurrent requests, one retry, sign-out when the refresh fails). Every endpoint function is checked for its method, path and body. | `tests/services/api.test.js` |

Results on 2026-09-24 (`npm run test:coverage`, see `test-results/frontend/`):

| | |
| --- | --- |
| Tests | 168 passed, 1 expected failure (a known bug, below), 15 files, about 80 s |
| Coverage of `src/` | 97% statements, 93% branches, 97% lines (`main.jsx` excluded) |

Every page and component is above 90% except `App.jsx` (83%: the 30-second poll timer and the role-guard fallbacks for pages a role cannot open) and `HomePage.jsx` (82%).

**Finding: an employee whose message fails to post sees no error.** In `TicketPage.jsx` the error box for actions (`actionError`) is rendered inside the "Actions" card, which only staff get. An employee posting on a closed ticket, or hitting any other error, gets nothing. The test `shows the backend error when posting fails (employee)` is marked `it.fails` and will start failing (that is, passing) once the Alert moves out of that card.

See [frontend/tests/README.md](../frontend/tests/README.md) for the layout and how to add a test.

## Known gaps

- **End-to-end tests in a browser.** The guide asks for Cypress or Selenium driving the real app. Nothing does that: pages are tested against a mocked API, the API client against a mocked `fetch`, and `bin/smoke-test.sh` exercises the real backend over HTTP without the UI. Playwright against the local stack would close this.
- **Load beyond 15 new users per second.** The full profile passed with headroom; the `heavy` profile has not been run yet, and CloudWatch was not watched during the run.
- **Migration upgrade paths.** `migrations/function.py` contains code that upgrades databases built by earlier schema versions (old locations table, `RESTRICT` to `SET NULL`, adding `assigned`, branches, basements, `db_admin`). The tests only build a schema from nothing and re-run it; they do not build an old-shape database first, so those branches are untested.
- **Concurrency.** The services lock rows (`FOR UPDATE` / `FOR SHARE`) so two admins cannot both pass an "already assigned" check. The tests confirm the lock is requested but do not run two requests at the same moment against one row.
- **Token expiry over real time.** Access-token expiry is tested by minting an already-expired token, not by waiting 15 minutes.
- **Cloud-only behaviour.** `IS_LOCAL=false` paths (`sslmode=require`, the missing `JWT_SECRET` error) are unit-tested but never run against Aurora.

## Observations from writing the tests

Things the tests confirmed about the code that a reader of API.md might not expect. None are failures.

- Deleting a user whose ticket is in status `assigned` clears `assigned_to` (via `ON DELETE SET NULL`) but leaves the status as `assigned`, so the ticket shows as assigned to nobody until an admin touches it. API.md says the ticket "goes back to unassigned", which is true of the assignee but not of the status.
- Building names sort by the database collation. The list test uses names of one case so it does not depend on whether upper-case sorts before lower-case.
- A `db_admin` is deliberately not facilities staff: they get 404 on tickets they did not report, cannot be assigned, and get 403 on the statistics. The tests pin this down.

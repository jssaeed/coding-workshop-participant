# Frontend tests

Vitest with React Testing Library, in a jsdom browser. Run from `frontend/`:

```sh
npm test                 # everything, once
npm run test:watch       # re-run on change
npm run test:coverage    # with a coverage report (text, and html in ../test-results/frontend/coverage/)
```

Results are written to `../test-results/frontend/`: `junit.xml` on every run, and the coverage report (HTML plus `coverage-summary.json`) with `test:coverage`. The folder is ignored by git.

## Layout

The folder mirrors `src/`:

| Folder | What is tested | How |
| --- | --- | --- |
| `services/` | `format.js` (display helpers) and `api.js` (the backend client) | Pure functions, and `fetch` replaced with a mock so URLs, headers, error handling and the expired-token refresh can be checked exactly |
| `components/` | `Alert`, `TicketProgress`, `AppHeader`, the charts | Rendered on their own with props |
| `pages/` | Every page | Rendered with `src/services/api.js` mocked, so a test says what the backend answers and checks what the page shows and sends |
| `App.test.jsx` | The app shell | Sign-in state, navigation, header polling |

`helpers.jsx` holds the fixtures (users of every role, a building, a ticket, a message), the mock of the API module, `pageOf(items, total)` and `threadOf(items, total, hasMore)` for the one-page shapes the list endpoints answer with, and two helpers for Ant Design's `Select`, which is not a native `<select>`: `chooseOption(combobox, text)` and `openedOptions(combobox)`.

`setup.js` runs before each file: it loads the jest-dom matchers, stubs `matchMedia` and `ResizeObserver` (Ant Design needs them, jsdom lacks them) and unmounts everything after each test.

## Writing a page test

```jsx
vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())
import * as api from '../../src/services/api'
import { resetApi, ticket } from '../helpers'

beforeEach(() => resetApi(api))          // empty lists, zero counts

it('lists my tickets', async () => {
  api.incidents.list.mockResolvedValue([ticket({ id: 12 })])
  render(<TicketsPage user={employee} onOpen={vi.fn()} />)
  expect(await screen.findByText('Leaking pipe')).toBeInTheDocument()
})
```

Prefer queries a user would recognise (text, labels, roles). Wait for asynchronous updates with `findBy*` or `waitFor`; a page that has just changed a form value may not have re-rendered yet.

## Known gaps

- No end-to-end tests: nothing drives the real app in a real browser. The pages are tested against a mocked API, and the API against a mocked `fetch`; `bin/smoke-test.sh` covers the real backend over HTTP but never the UI.
- `main.jsx` (the theme and the root render) is excluded from coverage.

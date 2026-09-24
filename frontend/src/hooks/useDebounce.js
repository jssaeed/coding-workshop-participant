import { useEffect, useState } from 'react'

// Returns `value` once it has stopped changing for `delay` milliseconds.
// A search box uses it so the server gets one request per pause in typing
// instead of one per keystroke.
export default function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer) // the value changed again: start over
  }, [value, delay])

  return debounced
}

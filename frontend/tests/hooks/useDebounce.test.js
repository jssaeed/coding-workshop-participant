import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import useDebounce from '../../src/hooks/useDebounce'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useDebounce', () => {
  it('starts with the value and only follows it after the delay', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 300), { initialProps: { value: 'a' } })
    expect(result.current).toBe('a')
    rerender({ value: 'ab' })
    expect(result.current).toBe('a')
    act(() => vi.advanceTimersByTime(299))
    expect(result.current).toBe('a')
    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe('ab')
  })

  it('restarts the wait every time the value changes', () => {
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 300), { initialProps: { value: '' } })
    rerender({ value: 'l' })
    act(() => vi.advanceTimersByTime(200))
    rerender({ value: 'le' })
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe('') // 400ms passed, but never 300ms without a change
    act(() => vi.advanceTimersByTime(100))
    expect(result.current).toBe('le')
  })
})

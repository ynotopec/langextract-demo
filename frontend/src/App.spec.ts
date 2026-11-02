import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import App from './App.vue'
import { apiRequest } from './api'

const defaults = { prompt: 'Extraire les organisations.', extraction_passes: 2, max_workers: 8, max_char_buffer: 1200, include_text: false }
let wrapper: VueWrapper
const fetchMock = vi.fn()
const reply = (data: unknown, status = 200) => ({ ok: status < 400, status, json: async () => data })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:synthetic-export'), revokeObjectURL: vi.fn() })
  fetchMock.mockReset()
  wrapper = mount(App)
})
afterEach(() => { wrapper.unmount(); vi.unstubAllGlobals() })

async function connect() {
  fetchMock.mockResolvedValueOnce(reply({ defaults, max_upload_bytes: 20 * 1024 * 1024 }))
  await wrapper.get('input[type="password"]').setValue('synthetic-ui-token')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}
async function selectPdf() {
  Object.defineProperty(wrapper.get('input[type="file"]').element, 'files', { value: [new File(['%PDF-test'], 'test.pdf', { type: 'application/pdf' })] })
  await wrapper.get('input[type="file"]').trigger('change')
}

describe('document extraction', () => {
  it('keeps token in memory and authenticates requests', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    await connect()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/config')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer synthetic-ui-token')
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
    expect(storage).not.toHaveBeenCalled()
  })

  it('uploads PDF/options and renders warnings, escaped text and downloadable exports', async () => {
    await connect()
    await selectPdf()
    fetchMock.mockResolvedValueOnce(reply({
      document: { text: '<script>evil()</script>', extractions: [{ extraction_class: 'org', extraction_text: '<script>evil()</script>', char_interval: { start_pos: 0, end_pos: 22 } }] },
      jsonl: '{}\n', html: '<script>evil()</script>', warnings: ['Pages ignorées : 2'], text: null,
    }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const request = fetchMock.mock.calls[1][1]
    expect(request.body.get('file').name).toBe('test.pdf')
    expect(JSON.parse(request.body.get('options'))).toEqual(defaults)
    expect(wrapper.text()).toContain('Pages ignorées : 2')
    expect(wrapper.findAll('a[download]')).toHaveLength(2)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('<script>evil()</script>')
    await wrapper.findAll('button').find(button => button.text() === 'Se déconnecter')!.trigger('click')
    expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe('')
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    expect(wrapper.find('a[download]').exists()).toBe(false)
  })

  it('shows an actionable busy error and allows retry', async () => {
    await connect()
    await selectPdf()
    fetchMock.mockResolvedValueOnce(reply({ detail: 'Une extraction est déjà en cours.' }, 503))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Une extraction est déjà en cours.')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('rejects an invalid token', async () => {
    fetchMock.mockResolvedValueOnce(reply({ detail: 'Token absent ou invalide.' }, 401))
    await wrapper.get('input[type="password"]').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Token absent ou invalide.')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
  })

  it('handles non-JSON reverse proxy errors', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502, json: async () => { throw new Error('HTML gateway error') } })
    await expect(apiRequest('config', 'synthetic-ui-token')).rejects.toThrow('Erreur HTTP 502')
  })
})

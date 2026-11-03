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
    expect(wrapper.html()).toContain('&lt;script&gt;evil()&lt;/script&gt;')
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('tbody').text()).toContain('<script>evil()</script>')
    await wrapper.findAll('button').find(button => button.text() === 'Se déconnecter')!.trigger('click')
    expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe('')
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    expect(wrapper.find('a[download]').exists()).toBe(false)
  })

  it('uses matching category colors, counts and visible labels in the legend, table and Unicode highlights', async () => {
    await connect()
    await selectPdf()
    const extractions = [
      { extraction_class: 'org', extraction_text: 'ACME', char_interval: { start_pos: 2, end_pos: 6 } },
      { extraction_class: 'amount', extraction_text: '42', char_interval: { start_pos: 7, end_pos: 9 } },
      { extraction_class: 'person', extraction_text: 'Alice', char_interval: { start_pos: 10, end_pos: 15 } },
    ]
    const complete = async (items: typeof extractions) => {
      fetchMock.mockResolvedValueOnce(reply({ document: { text: '😀 ACME 42 Alice', extractions: items }, jsonl: '{}', html: '', warnings: [] }))
      await wrapper.get('form').trigger('submit')
      await flushPromises()
    }
    await complete(extractions)
    const legend = wrapper.get('[aria-label="Légende des catégories"]')
    expect(legend.findAll('li')).toHaveLength(3)
    expect(legend.text()).toContain('Organisation (org) · 1')
    const colors = new Map<string, string>()
    for (const [index, entity] of extractions.entries()) {
      const badge = wrapper.findAll('tbody .entity-category')[index]!
      const mark = wrapper.findAll('.entity-highlight')[index]!
      colors.set(entity.extraction_class, badge.attributes('style') ?? '')
      expect(mark.attributes('style')).toBe(badge.attributes('style'))
      expect(legend.findAll('.entity-category')[index]!.attributes('style')).toBe(badge.attributes('style'))
      expect(mark.get('small').text()).toBe(badge.text())
      expect(mark.element.firstChild?.textContent).toBe(entity.extraction_text)
    }
    expect(new Set(colors.values()).size).toBe(3)
    expect(wrapper.get('.document-text').element.parentElement?.hasAttribute('open')).toBe(true)
    // The same class must retain its color when order or document changes.
    await complete([...extractions].reverse())
    for (const [index, entity] of [...extractions].reverse().entries()) {
      expect(wrapper.findAll('tbody .entity-category')[index]!.attributes('style')).toBe(colors.get(entity.extraction_class))
    }
  })

  it('escapes custom category labels and never puts category text into CSS', async () => {
    await connect()
    await selectPdf()
    const category = '<script>evil()</script>;color:red'
    fetchMock.mockResolvedValueOnce(reply({ document: { text: 'ACME', extractions: [
      { extraction_class: category, extraction_text: 'ACME', char_interval: { start_pos: 0, end_pos: 4 } },
    ] }, jsonl: '{}', html: '', warnings: [] }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('.entity-highlight small').text()).toBe(category)
    expect(wrapper.find('script').exists()).toBe(false)
    for (const badge of wrapper.findAll('.entity-category, .entity-highlight')) {
      expect(badge.attributes('style')).not.toContain('evil')
      expect(badge.attributes('style')).not.toContain('color:red')
      expect(badge.attributes('style')).toContain('var(--background-contrast-')
    }
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

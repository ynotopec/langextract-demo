<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { DsfrAlert, DsfrButton, DsfrInput } from '@gouvminint/vue-dsfr'
import { apiRequest, type Options, type Result } from './api'

const token = ref('')
const connected = ref(false)
const busy = ref(false)
const error = ref('')
const file = ref<File>()
const maxUpload = ref(0)
const options = ref<Options>({ prompt: '', extraction_passes: 2, max_workers: 8, max_char_buffer: 1200, include_text: false })
const result = ref<Result>()
const downloads = ref<{ jsonl: string; html: string }>()
const entities = computed(() => result.value?.document.extractions ?? [])
// Build safe text nodes and marks from offsets; never inject model/PDF HTML.
const highlighted = computed(() => {
  const text = result.value?.document.text ?? ''
  const segments: { text: string; label?: string }[] = []
  let cursor = 0
  for (const entity of [...entities.value].sort((a, b) => (a.char_interval?.start_pos ?? 0) - (b.char_interval?.start_pos ?? 0))) {
    const interval = entity.char_interval
    if (!interval || interval.start_pos < cursor || interval.end_pos > text.length || interval.end_pos <= interval.start_pos) continue
    segments.push({ text: text.slice(cursor, interval.start_pos) })
    segments.push({ text: text.slice(interval.start_pos, interval.end_pos), label: entity.extraction_class })
    cursor = interval.end_pos
  }
  segments.push({ text: text.slice(cursor) })
  return segments
})
const controller = new AbortController()

function clearResult() {
  if (downloads.value) Object.values(downloads.value).forEach(URL.revokeObjectURL)
  downloads.value = undefined
  result.value = undefined
}
onUnmounted(() => { controller.abort(); clearResult() })

async function connect() {
  error.value = ''
  busy.value = true
  try {
    const config = await apiRequest<{ defaults: Options; max_upload_bytes: number }>('config', token.value, { signal: controller.signal })
    options.value = config.defaults
    maxUpload.value = config.max_upload_bytes
    connected.value = true
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
function disconnect() {
  token.value = ''
  file.value = undefined
  connected.value = false
  error.value = ''
  clearResult()
}
function chooseFile(event: Event) {
  clearResult()
  error.value = ''
  file.value = (event.target as HTMLInputElement).files?.[0]
}
async function extract() {
  if (!file.value) return
  clearResult()
  error.value = ''
  if (file.value.size > maxUpload.value) {
    error.value = 'Le PDF dépasse la taille autorisée.'
    return
  }
  busy.value = true
  const body = new FormData()
  body.append('file', file.value)
  body.append('options', JSON.stringify(options.value))
  try {
    result.value = await apiRequest<Result>('extractions', token.value, { method: 'POST', body, signal: controller.signal })
    downloads.value = {
      jsonl: URL.createObjectURL(new Blob([result.value.jsonl], { type: 'application/x-ndjson' })),
      html: URL.createObjectURL(new Blob([result.value.html], { type: 'text/html' })),
    }
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="fr-skiplinks"><div class="fr-container"><a class="fr-link" href="#contenu">Aller au contenu</a></div></div>
  <header class="fr-container fr-py-3w" role="banner">
    <p class="fr-text--bold fr-mb-0">LangExtract · Extraction de documents</p>
  </header>
  <main id="contenu" class="fr-container fr-py-6w" tabindex="-1">
    <h1>Extraire les informations d’un PDF</h1>
    <p class="fr-text--lead">Déposez votre document, précisez les informations recherchées et exportez les résultats.</p>
    <DsfrAlert v-if="error" type="error" title="L’opération a échoué" :description="error" role="alert" class="fr-mb-3w" />
    <form v-if="!connected" class="fr-col-12 fr-col-md-6" @submit.prevent="connect">
      <DsfrInput v-model="token" label="Token d’accès à l’API" label-visible type="password" required autocomplete="off" hint="Le token reste uniquement en mémoire jusqu’à la fermeture de la page ou la déconnexion." class="fr-mb-3w" />
      <DsfrButton type="submit" :disabled="busy || !token">{{ busy ? 'Vérification…' : 'Se connecter' }}</DsfrButton>
    </form>
    <template v-else>
      <div class="fr-mb-3w"><DsfrButton secondary :disabled="busy" @click="disconnect">Se déconnecter</DsfrButton></div>
      <form :aria-busy="busy" @submit.prevent="extract">
        <fieldset :disabled="busy" class="fr-fieldset">
          <legend class="fr-fieldset__legend fr-h4">Document et instructions</legend>
          <div class="fr-fieldset__element fr-upload-group">
            <label class="fr-label" for="pdf">Document PDF <span class="fr-hint-text">Taille maximale : {{ Math.floor(maxUpload / 1024 / 1024) }} Mo. Les PDF scannés nécessitent un OCR préalable.</span></label>
            <input id="pdf" class="fr-upload" type="file" accept="application/pdf,.pdf" required @change="chooseFile" />
          </div>
          <div class="fr-fieldset__element">
            <DsfrInput v-model="options.prompt" label="Instructions d’extraction" label-visible is-textarea required :maxlength="10000" :rows="10" />
          </div>
          <div class="fr-fieldset__element">
            <details>
              <summary class="fr-mb-2w">Paramètres avancés</summary>
              <div class="fr-grid-row fr-grid-row--gutters">
                <div class="fr-col-12 fr-col-md-4"><DsfrInput v-model.number="options.extraction_passes" label="Passes d’extraction" label-visible type="number" :min="1" :max="5" required /></div>
                <div class="fr-col-12 fr-col-md-4"><DsfrInput v-model.number="options.max_workers" label="Requêtes parallèles" label-visible type="number" :min="1" :max="24" required /></div>
                <div class="fr-col-12 fr-col-md-4"><DsfrInput v-model.number="options.max_char_buffer" label="Caractères par segment" label-visible type="number" :min="500" :max="4000" required /></div>
              </div>
              <div class="fr-checkbox-group fr-mt-3w"><input id="include-text" v-model="options.include_text" type="checkbox" /><label class="fr-label" for="include-text">Inclure le texte extrait dans le résultat</label></div>
            </details>
          </div>
          <div class="fr-fieldset__element"><DsfrButton type="submit" :disabled="busy || !file">{{ busy ? 'Extraction en cours…' : 'Lancer l’extraction' }}</DsfrButton></div>
        </fieldset>
      </form>
      <p role="status" aria-live="polite">{{ busy ? 'Traitement du document en cours. Cette opération peut prendre plusieurs minutes.' : result ? 'Extraction terminée.' : '' }}</p>
      <section v-if="result" aria-labelledby="results-title">
        <h2 id="results-title">Résultats</h2>
        <DsfrAlert v-for="warning in result.warnings" :key="warning" type="warning" title="Vérification nécessaire" :description="warning" class="fr-mb-2w" />
        <p>{{ entities.length }} entité(s) extraite(s). Vérifiez les informations avant de les réutiliser.</p>
        <ul v-if="downloads" class="fr-btns-group fr-btns-group--inline-md">
          <li><a class="fr-btn fr-btn--secondary" :href="downloads.jsonl" download="extractions.jsonl">Télécharger le JSONL</a></li>
          <li><a class="fr-btn fr-btn--secondary" :href="downloads.html" download="visualization_langextract.html">Télécharger la visualisation HTML</a></li>
        </ul>
        <div v-if="entities.length" class="fr-table"><table><caption>Entités extraites du document</caption><thead><tr><th scope="col">Classe</th><th scope="col">Extrait</th></tr></thead><tbody><tr v-for="(entity, index) in entities" :key="index"><td>{{ entity.extraction_class }}</td><td>{{ entity.extraction_text }}</td></tr></tbody></table></div>
        <details class="fr-mb-3w"><summary>Résumé JSON</summary><pre>{{ JSON.stringify(result.document, null, 2) }}</pre></details>
        <details v-if="result.text" class="fr-mb-3w"><summary>Texte extrait</summary><pre>{{ result.text }}</pre></details>
        <details v-if="result.document.text" class="fr-mb-3w">
          <summary>Visualisation des entités dans le texte</summary>
          <p class="document-text"><template v-for="(segment, index) in highlighted" :key="index"><mark v-if="segment.label" :title="segment.label">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></p>
        </details>
      </section>
    </template>
  </main>
  <footer class="fr-container fr-py-3w"><p class="fr-text--sm">Les documents sont transmis au fournisseur de modèle configuré par l’administrateur. Aucun historique n’est conservé par l’application. Les exports sont enregistrés sur votre poste.</p></footer>
</template>

<style scoped>
pre, .document-text { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>

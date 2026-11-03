import type { CSSProperties } from 'vue'

// DSFR token pairs support both light and dark themes. Known classes keep
// their color across documents, regardless of extraction order or omissions.
const definitions = [
  ['person', 'Personne', 'pink-macaron'],
  ['org', 'Organisation', 'blue-france'],
  ['invoice', 'Facture', 'purple-glycine'],
  ['date', 'Date', 'green-emeraude'],
  ['amount', 'Montant', 'yellow-tournesol'],
  ['email', 'E-mail', 'blue-cumulus'],
  ['iban', 'IBAN', 'brown-caramel'],
  ['address', 'Adresse', 'orange-terre-battue'],
  ['phone', 'Téléphone', 'green-bourgeon'],
  ['ref', 'Référence', 'beige-gris-galet'],
] as const
const categories = new Map<string, { label: string; color: string }>(
  definitions.map(([name, label, color]) => [name, { label, color }]),
)

export function categoryLabel(category: string): string {
  const known = categories.get(category)
  return known ? `${known.label} (${category})` : category
}

export function categoryStyle(category: string): CSSProperties {
  // Custom categories also have a stable color. Never interpolate model text
  // into CSS: the selected token always comes from our fixed palette.
  let hash = 0
  for (const char of category) hash = (hash * 31 + char.codePointAt(0)!) >>> 0
  const color = categories.get(category)?.color ?? definitions[hash % definitions.length]![2]
  return {
    backgroundColor: `var(--background-contrast-${color})`,
    color: `var(--text-label-${color})`,
    borderColor: `var(--border-default-${color})`,
  }
}

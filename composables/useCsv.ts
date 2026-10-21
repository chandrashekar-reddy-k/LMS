/** Build and download a CSV in the browser (UTF-8 with BOM so Excel shows ₦ and accents correctly). */
export const toCsv = (rows: (string | number | null | undefined)[][]) => {
  const esc = (v: string | number | null | undefined) => {
    const t = v === null || v === undefined ? '' : String(v)
    const safe = /^[=+\-@\t\r]/.test(t) ? `'${t}` : t   // stop spreadsheets treating cells as formulas
    return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
  }
  return rows.map(r => r.map(esc).join(',')).join('\r\n')
}

export const downloadCsv = (filename: string, rows: (string | number | null | undefined)[][]) => {
  const url = URL.createObjectURL(new Blob(['﻿' + toCsv(rows)], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** "Python Programming: Zero to Hero" -> "python-programming-zero-to-hero" */
export const fileSlug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'export'

// Renders a Topic's LectureContent (Markdown + a few custom directives) to HTML.
//
// - Maths: `$…$` inline and `$$…$$` block, typeset with KaTeX.
// - Callout box:  ::: callout Optional title
//                 body
//                 :::
// - Worked example: ::: example Optional title … :::
// - Images: standard `![alt](/media/…)` — nginx serves `/media/` directly.
//
// Raw HTML in the source is disabled: content is admin-authored but this keeps
// the lecture reader a pure Markdown surface (no embedded scripts/styles).

import MarkdownIt from 'markdown-it'
import container from 'markdown-it-container'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const md = new MarkdownIt({ html: false })

md.use(texmath, {
  engine: katex,
  delimiters: 'dollars',
  katexOptions: { throwOnError: false },
})

// `::: <name> [title]` … `:::` → <div class="lecture-<name>"> with an optional
// heading paragraph. One helper, registered once per directive name.
function directive(name) {
  md.use(container, name, {
    render(tokens, idx) {
      const token = tokens[idx]
      if (token.nesting !== 1) return '</div>\n'
      const title = token.info.trim().slice(name.length).trim()
      const heading = title
        ? `<p class="lecture-${name}__title">${md.utils.escapeHtml(title)}</p>\n`
        : ''
      return `<div class="lecture-${name}">\n${heading}`
    },
  })
}

directive('callout')
directive('example')

export function renderLecture(markdown) {
  return md.render(markdown ?? '')
}

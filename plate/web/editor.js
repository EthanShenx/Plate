import { EditorState } from "@codemirror/state";
import { EditorView, basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { r } from "@codemirror/legacy-modes/mode/r";
import { tags } from "@lezer/highlight";

const highlighting = HighlightStyle.define([
  { tag: tags.comment, color: "var(--muted)", fontStyle: "italic" },
  { tag: [tags.keyword, tags.operatorKeyword], color: "#354c85" },
  { tag: [tags.string, tags.regexp, tags.special(tags.string)], color: "#236246" },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: "var(--amber-12)" },
  { tag: [tags.function(tags.variableName), tags.definition(tags.variableName), tags.typeName],
    color: "#324264" },
  { tag: tags.invalid, color: "var(--red-11)" },
  { tag: tags.escape, color: "var(--red-12)" },
]);

export function createEditor(parent, language, source, onChange) {
  let replacing = false;
  const editor = new EditorView({
    parent,
    state: EditorState.create({
      doc: source,
      extensions: [
        basicSetup,
        syntaxHighlighting(highlighting),
        language === "script-r" ? StreamLanguage.define(r) : python(),
        EditorView.lineWrapping,
        EditorView.contentAttributes.of({ "aria-label": "Panel script", spellcheck: "false" }),
        EditorView.updateListener.of(update => {
          if (update.docChanged && !replacing) onChange(update.state.doc.toString());
        }),
      ],
    }),
  });
  return {
    replace(source) {
      if (source === editor.state.doc.toString()) return;
      replacing = true;
      editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: source } });
      replacing = false;
    },
    destroy() { editor.destroy(); },
  };
}

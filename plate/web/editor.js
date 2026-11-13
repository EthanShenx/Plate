import { EditorState } from "@codemirror/state";
import { EditorView, basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { StreamLanguage } from "@codemirror/language";
import { r } from "@codemirror/legacy-modes/mode/r";

export function createEditor(parent, language, source, onChange) {
  let replacing = false;
  const editor = new EditorView({
    parent,
    state: EditorState.create({
      doc: source,
      extensions: [
        basicSetup,
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

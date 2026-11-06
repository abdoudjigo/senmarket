"""Tiny helper: build a notebook from a list of ("md" | "code", text) cells."""
import nbformat as nbf


def build(path, cells):
    nb = nbf.v4.new_notebook()
    nb.cells = [
        nbf.v4.new_markdown_cell(t.strip()) if k == "md" else nbf.v4.new_code_cell(t.strip())
        for k, t in cells
    ]
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nbf.write(nb, path)

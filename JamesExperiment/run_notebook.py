"""Execute the configured notebook, preserving outputs even after failures."""
from pathlib import Path
import os
import sys
import time


def main():
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
    import nbformat
    from nbclient import NotebookClient
    from jupyter_client import KernelManager

    root = Path(__file__).resolve().parents[1]
    notebook = root / 'JamesExperiment' / 'patch_sampling_pipeline(JAMES).ipynb'
    nb = nbformat.read(notebook, as_version=4)
    km = KernelManager(kernel_name='python3')
    km.kernel_spec.argv[0] = sys.executable
    logdir = root / 'outputs' / 'JamesExperiment'
    logdir.mkdir(parents=True, exist_ok=True)
    status = logdir / 'notebook_run_status.txt'
    def save():
        nbformat.write(nb, notebook)
        nbformat.write(nb, notebook.with_name('slide_sampling_pipeline(JAMES).ipynb'))
    def started(cell, cell_index, **kwargs):
        message = f'Running cell {cell_index}: {cell.source.splitlines()[0][:120]}'
        print(message, flush=True)
        status.write_text(message, encoding='utf-8')
    def finished(cell, cell_index, **kwargs):
        for output in cell.get('outputs', []):
            if output.output_type == 'stream':
                print(output.text[-5000:], flush=True)
        save()
    client = NotebookClient(nb, km=km, timeout=None,
                            resources={'metadata': {'path': str(root)}},
                            on_cell_start=started, on_cell_executed=finished)
    try:
        client.execute()
    except Exception as exc:
        status.write_text(f'FAILED: {exc}', encoding='utf-8')
        raise
    else:
        status.write_text('COMPLETE: both tensors saved and notebook verification passed.', encoding='utf-8')
        print('NOTEBOOK COMPLETE', flush=True)
    finally:
        save()
        if km.has_kernel:
            km.shutdown_kernel(now=True)


if __name__ == '__main__':
    main()

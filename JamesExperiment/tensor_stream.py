"""Write ordinary CPU float32 torch tensors with bounded memory.

Uses PyTorch's ZIP tensor serialization layout. Each supplied batch is written
directly to the final storage entry; no full tensor or duplicate disk buffer.
The result supports torch.load(..., weights_only=True, mmap=True).
"""
from collections import OrderedDict
import io
import math
from pathlib import Path
import pickle
import sys
import zipfile


class BatchTensor:
    """Read-only disk tensor; indexing returns an ordinary copied torch batch.

    Unlike Windows torch.load(mmap=True), ACCESS_READ does not reserve commit
    memory for the full file. The saved .pt remains a standard PyTorch tensor.
    """
    def __init__(self, path):
        import numpy as np
        import torch
        path = Path(path)
        metadata = torch.load(path, weights_only=True, map_location='meta')
        if metadata.dtype != torch.float32 or not metadata.is_contiguous() or metadata.storage_offset():
            raise ValueError('Expected a contiguous float32 tensor with zero storage offset.')
        self.shape = metadata.shape
        self.dtype = metadata.dtype
        with zipfile.ZipFile(path) as archive:
            entries = [item for item in archive.infolist() if item.filename.endswith('/data/0')]
            if len(entries) != 1 or entries[0].compress_type != zipfile.ZIP_STORED:
                raise ValueError('Expected one uncompressed tensor storage.')
            entry = entries[0]
            if entry.file_size != math.prod(self.shape) * 4:
                raise ValueError('Tensor storage size disagrees with its shape.')
            with path.open('rb') as handle:
                handle.seek(entry.header_offset)
                header = handle.read(30)
            offset = entry.header_offset + 30 + int.from_bytes(header[26:28], 'little') + int.from_bytes(header[28:30], 'little')
        self._array = np.memmap(path, dtype=np.float32, mode='r', offset=offset, shape=tuple(self.shape))

    def __len__(self):
        return self.shape[0]

    def __getitem__(self, index):
        import numpy as np
        import torch
        return torch.from_numpy(np.array(self._array[index], copy=True))


def open_batch_tensor(path):
    return BatchTensor(path)


def save_float_tensor(path, shape, batches):
    import numpy as np
    import torch

    shape = tuple(shape)
    count = math.prod(shape)
    storage = torch.empty(0).untyped_storage()
    strides = tuple(math.prod(shape[i + 1:]) for i in range(len(shape)))

    class TensorReference:
        def __reduce__(self):
            return (torch._utils._rebuild_tensor_v2,
                    (storage, 0, shape, strides, False, OrderedDict()))

    class TensorPickler(pickle.Pickler):
        def persistent_id(self, value):
            if value is storage:
                return ('storage', torch.FloatStorage, '0', 'cpu', count)
            return None

    metadata = io.BytesIO()
    TensorPickler(metadata, protocol=2).dump(TensorReference())
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.partial')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr('tensor/data.pkl', metadata.getvalue())
        archive.writestr('tensor/byteorder', sys.byteorder)
        archive.writestr('tensor/version', '3\n')
        written = 0
        with archive.open('tensor/data/0', 'w', force_zip64=True) as target:
            for batch in batches:
                array = np.ascontiguousarray(batch, dtype=np.float32)
                written += array.size
                if written > count:
                    raise ValueError('Too many tensor values.')
                target.write(memoryview(array).cast('B'))
        if written != count:
            raise ValueError(f'Expected {count} tensor values; received {written}.')
    temporary.replace(path)
    return path

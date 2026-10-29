"""Small feature-token Transformer and training/evaluation for HEST regression."""

from pathlib import Path

import json

import csv

import os

import tempfile





def build_model(n_components=250, n_genes=50, d_model=64, n_heads=4, n_layers=2,

                dropout=0.1):

    """Each PCA component is a scalar token; predict all selected genes jointly."""

    import torch

    from torch import nn



    class PatchExpressionTransformer(nn.Module):

        def __init__(self):

            super().__init__()

            self.input_projection = nn.Linear(1,d_model)

            self.position = nn.Parameter(torch.zeros(1,n_components,d_model))

            layer=nn.TransformerEncoderLayer(d_model=d_model,nhead=n_heads,

                     dim_feedforward=d_model*2,dropout=dropout,batch_first=True,

                     activation='gelu',norm_first=True)

            self.encoder=nn.TransformerEncoder(layer,num_layers=n_layers,

                                               enable_nested_tensor=False)

            self.norm=nn.LayerNorm(d_model)

            self.head=nn.Sequential(nn.Linear(d_model,d_model),nn.GELU(),nn.Linear(d_model,n_genes))



        def forward(self,x):

            if x.ndim!=2 or x.shape[1]!=n_components:

                raise ValueError(f'Expected input [batch,{n_components}], got {tuple(x.shape)}')

            tokens=self.input_projection(x.unsqueeze(-1))+self.position

            return self.head(self.norm(self.encoder(tokens).mean(dim=1)))

    return PatchExpressionTransformer()





def train_transformer(x_train_path,y_train_path,x_test_path,y_test_path,

                      output_dir,epochs=30,batch_size=256,learning_rate=1e-3,

                      d_model=64,n_heads=4,n_layers=2,dropout=0.1,seed=42,

                      device=None):

    """Fit on training tensors, report held-out test MSE each epoch, save model and metrics.



    X inputs must already have been PCA transformed with PCA fitted on training

    embeddings only. Y tensors are [patches, top_genes] log-relative expression.

    Test loss is diagnostic only; test data never update weights or select a model.

    train_loss averages training-mode batch MSEs weighted by patch count.

    test_loss uses evaluation mode. CSV/JSON loss history is saved each epoch.

    """

    import numpy as np

    import torch

    from torch.utils.data import DataLoader,TensorDataset

    import torch.nn.functional as F

    if isinstance(epochs,bool) or not isinstance(epochs,int) or epochs<1:

        raise ValueError('epochs must be a positive integer.')

    if isinstance(batch_size,bool) or not isinstance(batch_size,int) or batch_size<1:

        raise ValueError('batch_size must be a positive integer.')

    torch.manual_seed(seed)

    np.random.seed(seed)

    target_device=torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))

    if target_device.type=='cuda' and not torch.cuda.is_available():

        raise RuntimeError('CUDA was requested but is unavailable.')

    def load_tensor(path):

        # Tensors produced by this pipeline are plain tensors; map_location avoids

        # depending on the device used during extraction.

        try: return torch.load(path,map_location='cpu',weights_only=True).float()

        except TypeError: return torch.load(path,map_location='cpu').float()

    xtr,ytr,xte,yte=[load_tensor(p) for p in (x_train_path,y_train_path,x_test_path,y_test_path)]

    if any(t.ndim!=2 for t in (xtr,ytr,xte,yte)):

        raise ValueError('PCA features and expression targets must be rank-2 tensors.')

    if len(xtr)!=len(ytr) or len(xte)!=len(yte) or xtr.shape[1]!=xte.shape[1] or ytr.shape[1]!=yte.shape[1]:

        raise ValueError('Train/test feature and target shapes do not match.')

    if len(xtr)<1 or len(xte)<1:

        raise ValueError('Need nonempty train and test tensors.')

    # Preserve manifest order in the loader; the split itself is deterministic.

    train_loader=DataLoader(TensorDataset(xtr,ytr),batch_size=batch_size,shuffle=False)

    test_loader=DataLoader(TensorDataset(xte,yte),batch_size=batch_size,shuffle=False)

    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)

    model=build_model(xtr.shape[1],ytr.shape[1],d_model,n_heads,n_layers,dropout).to(target_device)

    optimizer=torch.optim.AdamW(model.parameters(),lr=learning_rate)

    history=[]

    for epoch in range(epochs):

        model.train(); total=0.0

        for xb,yb in train_loader:

            xb,yb=xb.to(target_device),yb.to(target_device)

            optimizer.zero_grad(set_to_none=True)

            loss=F.mse_loss(model(xb),yb)

            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)

            optimizer.step(); total+=loss.item()*len(xb)

        train_loss=total/len(xtr)

        model.eval()

        test_squared_error=0.0

        final_predictions=[]

        with torch.inference_mode():

            for xb,yb in test_loader:

                xb,yb=xb.to(target_device),yb.to(target_device)

                predicted=model(xb)

                test_squared_error+=F.mse_loss(predicted,yb,reduction='sum').item()

                if epoch+1==epochs:

                    final_predictions.append(predicted.cpu())

        test_loss=test_squared_error/yte.numel()

        history.append(dict(epoch=epoch+1,train_loss=train_loss,test_loss=test_loss,

                            train_mse=train_loss,test_mse=test_loss))

        _save_training_history(history,output)

        print(f'Epoch {epoch+1}/{epochs} | train_loss (MSE): {train_loss:.6f} | '

              f'test_loss (MSE): {test_loss:.6f}',flush=True)

    prediction=torch.cat(final_predictions)

    actual=yte

    pred_np,actual_np=prediction.numpy(),actual.numpy()

    pcc=[]

    for j in range(actual_np.shape[1]):

        a,b=pred_np[:,j],actual_np[:,j]

        pcc.append(float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else float('nan'))

    std=np.std(actual_np,axis=0,ddof=1) if len(actual_np)>1 else np.zeros(actual_np.shape[1])

    nmae=np.abs(pred_np-actual_np).mean(axis=0)/np.maximum(std,1e-8)

    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)

    config={'n_components':xtr.shape[1],'n_genes':ytr.shape[1],

            'd_model':d_model,'n_heads':n_heads,'n_layers':n_layers,'dropout':dropout,

            'seed':seed,'device':str(target_device),'epochs':epochs,

            'batch_size':batch_size,'learning_rate':learning_rate,'loss':'mse'}

    torch.save({'model_state_dict':model.cpu().state_dict(),

                'model_config':config},output/'patch_gene_transformer.pt')

    metrics={'train_loss':history[-1]['train_loss'],'test_loss':history[-1]['test_loss'],

             'mean_pcc':float(np.nanmean(pcc)),'per_gene_pcc':pcc,

             'mean_std_normalized_mae':float(np.mean(nmae)),

             'per_gene_std_normalized_mae':nmae.tolist(),'test_patches':len(xte),

             'history':history,'model_config':config}

    (output/'test_metrics.json').write_text(json.dumps(metrics,indent=2,allow_nan=True),encoding='utf-8')

    torch.save(prediction,output/'test_predictions.pt')

    plot_loss_history(history, output/'training_loss.png')
    return model,metrics







def _save_training_history(history,output_dir):

    """Persist completed epochs using replace-on-completion writes."""

    output=Path(output_dir)

    output.mkdir(parents=True,exist_ok=True)

    def atomic(name,writer):

        fd,temporary=tempfile.mkstemp(prefix=f'.{name}.',suffix='.tmp',dir=output)

        os.close(fd)

        try:

            writer(Path(temporary))

            os.replace(temporary,output/name)

        finally:

            Path(temporary).unlink(missing_ok=True)

    def write_csv(path):

        with path.open('w',encoding='utf-8',newline='') as handle:

            writer=csv.DictWriter(handle,fieldnames=['epoch','train_loss','test_loss','train_mse','test_mse'])

            writer.writeheader()

            writer.writerows(history)

    atomic('training_history.csv',write_csv)

    atomic('training_history.json',lambda p:p.write_text(json.dumps(history,indent=2),encoding='utf-8'))




def verify_training_tensors(x_train_path, y_train_path, x_test_path, y_test_path):
    """Inspect four plain tensors independently of the training/pipeline stages.

    Checks tensor type, rank, nonempty axes, finite values, matching X/Y rows,
    and shared feature/gene dimensions. No checkpoint/selection/split files are
    needed. Shape checks cannot establish patch or gene identity/order.
    """
    import torch
    paths = dict(train_x=x_train_path, train_y=y_train_path,
                 test_x=x_test_path, test_y=y_test_path)
    shapes, report = {}, []
    for name, value in paths.items():
        path = Path(value).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f'{name}: tensor file not found: {path}')
        try:
            tensor = torch.load(path, map_location='cpu', weights_only=True)
        except TypeError:
            tensor = torch.load(path, map_location='cpu')
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f'{name}: {path} must contain a plain torch.Tensor.')
        if tensor.ndim != 2 or min(tensor.shape) < 1:
            raise ValueError(f'{name}: expected nonempty [patches, features/genes], got {tuple(tensor.shape)}.')
        if not torch.isfinite(tensor).all():
            raise ValueError(f'{name}: NaN or infinite values in {path}.')
        shapes[name] = tuple(tensor.shape)
        report.append(dict(tensor=name, path=str(path), patches=tensor.shape[0],
                           columns=tensor.shape[1], dtype=str(tensor.dtype), finite=True))
        del tensor
    if shapes['train_x'][0] != shapes['train_y'][0]:
        raise ValueError('Training X and Y have different patch counts.')
    if shapes['test_x'][0] != shapes['test_y'][0]:
        raise ValueError('Test X and Y have different patch counts.')
    if shapes['train_x'][1] != shapes['test_x'][1]:
        raise ValueError('Training and test X have different feature counts.')
    if shapes['train_y'][1] != shapes['test_y'][1]:
        raise ValueError('Training and test Y have different gene counts.')
    return dict(files=report, train_patches=shapes['train_x'][0],
                test_patches=shapes['test_x'][0], n_components=shapes['train_x'][1],
                n_genes=shapes['train_y'][1])


def _prompt_tensor_path(label, default, filename):
    raw = input(f'{label} .pt file or containing folder [{default}]: ').strip()
    path = Path(raw.strip("\"'") if raw else default).expanduser()
    return path/filename if path.is_dir() else path


def prompt_tensor_paths(default_dir=str(Path(__file__).resolve().parent.parent / 'training_run')):
    """Ask for the four input files; no previous notebook state is used."""
    base = Path(default_dir)
    fields = [
        ('x_train_path', 'Training X', 'X_train_pca250.pt'),
        ('y_train_path', 'Training Y', 'y_train.pt'),
        ('x_test_path', 'Test X', 'X_test_pca250.pt'),
        ('y_test_path', 'Test Y', 'y_test.pt'),
    ]
    return {key: _prompt_tensor_path(label, base/name, name)
            for key, label, name in fields}


def prompt_training_config(default_dir=str(Path(__file__).resolve().parent.parent / 'training_run')):
    """Prompt for tensor paths and hyperparameters, without running verification."""
    import math
    paths = prompt_tensor_paths(default_dir)
    def number(label, default, conversion, valid, requirement):
        while True:
            raw = input(f'{label} [{default}]: ').strip()
            try:
                value = conversion(raw) if raw else default
                if not math.isfinite(value) or not valid(value):
                    raise ValueError
                return value
            except (ValueError, OverflowError):
                print(requirement)
    params = dict(
        epochs=number('Epochs', 30, int, lambda x:x>0, 'Enter a positive integer.'),
        batch_size=number('Batch size', 256, int, lambda x:x>0, 'Enter a positive integer.'),
        learning_rate=number('Learning rate', 1e-3, float, lambda x:x>0, 'Enter a positive finite number.'),
        d_model=number('Transformer dimension', 64, int, lambda x:x>0, 'Enter a positive integer.'),
    )
    params['n_heads'] = number('Attention heads', 4, int,
        lambda x:x>0 and params['d_model']%x==0,
        'Enter a positive integer that divides the transformer dimension.')
    params['n_layers'] = number('Transformer layers', 2, int, lambda x:x>0, 'Enter a positive integer.')
    params['dropout'] = number('Dropout', 0.1, float, lambda x:0<=x<1, 'Enter a number from 0 up to, but excluding, 1.')
    params['seed'] = number('Random seed', 42, int, lambda x:0<=x<2**32, 'Enter an integer from 0 to 4294967295.')
    while True:
        value = input('Device: auto / cpu / cuda [auto]: ').strip().lower() or 'auto'
        if value in ('auto', 'cpu', 'cuda'):
            params['device'] = None if value=='auto' else value
            break
        print('Enter auto, cpu, or cuda.')
    default_output = Path(default_dir)/'model'
    raw = input(f'Model output folder [{default_output}]: ').strip()
    params['output_dir'] = Path(raw.strip("\"'") if raw else default_output).expanduser()
    return dict(paths=paths, parameters=params)



def plot_loss_history(history, output_path=None):
    '''Display train/test MSE against epoch and optionally save a PNG.'''
    import matplotlib.pyplot as plt
    if not history:
        raise ValueError('No completed epochs are available to plot.')
    epochs = [row['epoch'] for row in history]
    train = [row['train_loss'] for row in history]
    test = [row['test_loss'] for row in history]
    fig, ax = plt.subplots(figsize=(8, 5))
    try:
        ax.plot(epochs, train, label='Training MSE')
        ax.plot(epochs, test, label='Test MSE')
        ax.set(xlabel='Epoch', ylabel='Mean squared error', title='Training and test loss')
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=150, bbox_inches='tight')
            print(f'Saved loss plot: {path}')
        plt.show()
    finally:
        plt.close(fig)

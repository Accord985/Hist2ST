"""Unambiguous human gene alignment using a saved official HGNC snapshot."""
from collections import defaultdict
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import urllib.request

HGNC_URL = 'https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt'


class HumanGeneMap:
    def __init__(self, path):
        self.path = Path(path)
        identifiers = defaultdict(set)
        aliases = defaultdict(set)
        with self.path.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle, delimiter='\t'))
        self.approved = {row['symbol'] for row in rows if row.get('status') == 'Approved'}
        for row in rows:
            if row.get('status') != 'Approved':
                continue
            symbol = row['symbol']
            for identifier in row.get('ensembl_gene_id', '').split('|'):
                if identifier:
                    identifiers[identifier].add(symbol)
            for field in ('alias_symbol', 'prev_symbol'):
                for alias in row.get(field, '').split('|'):
                    if alias:
                        aliases[alias].add(symbol)
        self.identifiers = {key: next(iter(values)) for key, values in identifiers.items() if len(values) == 1}
        self.aliases = {key: next(iter(values)) for key, values in aliases.items() if len(values) == 1}
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    @lru_cache(maxsize=262144)
    def canonical(self, gene):
        gene = str(gene).strip().lstrip('_')
        # HEST includes human/mouse reference prefixes on some human slides.
        # Remove only explicit human build labels; preserve mouse identifiers.
        gene = re.sub(r'^(?:GRCh37|GRCh38|hg19|hg38)__', '', gene, flags=re.IGNORECASE)
        gene = gene.lstrip('_')
        match = re.fullmatch(r'(ENSG\d+)(?:\.\d+)?(?:_PAR_Y)?', gene)
        if match:
            identifier = match.group(1)
            return self.identifiers.get(identifier, identifier)
        if gene in self.approved:
            return gene
        return self.aliases.get(gene, gene)

    def panel(self, names):
        return [self.canonical(gene) for gene in names]


def load_human_gene_map(path=None):
    path = (Path(path) if path else Path(__file__).resolve().parents[1]
            / 'data/JamesExperiment/annotations/hgnc_complete_set.tsv')
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.partial')
        with urllib.request.urlopen(HGNC_URL, timeout=90) as response, temporary.open('wb') as output:
            import shutil
            shutil.copyfileobj(response, output)
        temporary.replace(path)
    mapping = HumanGeneMap(path)
    path.with_suffix('.json').write_text(json.dumps(dict(
        source=HGNC_URL, sha256=mapping.sha256,
        policy='Approved symbols; uniquely mapped Ensembl IDs and aliases; preserve unresolved identifiers',
    ), indent=2), encoding='utf-8')
    return mapping


def align_columns(expression, source_names, target_names, mapping=None):
    """Align by canonical names, summing source features with the same gene."""
    positions = defaultdict(list)
    names = mapping.panel(source_names) if mapping else list(source_names)
    for index, name in enumerate(names):
        positions[name].append(index)
    values = expression[:, [positions[name][0] for name in target_names]].copy()
    for column, name in enumerate(target_names):
        for extra in positions[name][1:]:
            values[:, column] += expression[:, extra]
    return values

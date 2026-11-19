"""Record agent-selected findings without changing application code or business rules."""

from hashlib import sha256
from pathlib import Path
import re
import unicodedata

from harness.config import ConfigError
from harness.project import PROJECT_FILES
from harness.project_storage import PROJECT_LOCK, ProjectGit, atomic_write, local_path, project_lock

PENDING = '.harness/pendencias.md'
MEMORY = '.harness/memoria/problemas-conhecidos.md'
CATEGORIES = ('problema', 'risco', 'melhoria sugerida')
STATES = ('observado', 'hipótese', 'confirmado', 'aguardando avaliação', 'resolvido', 'descartado')
BLOCK = re.compile(r'^<!-- harness:finding:([a-f0-9]{64}) -->\r?\n.*?^<!-- /harness:finding -->\r?$', re.M | re.S)
FIELDS = {'relevant', 'component', 'problem', 'category', 'state', 'description', 'evidence',
          'impact', 'action', 'origin', 'persistent', 'benefit', 'tradeoff', 'confirmation'}


def _text(value, field, *, empty=False):
    if (not isinstance(value, str) or (not empty and not value.strip())
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or '<!--' in value):
        raise ConfigError(f'Expected a single-line finding field: {field}')
    return value.strip()


def _normal(value, *, fold_case=False):
    value = unicodedata.normalize('NFKC', value)
    return ' '.join((value.casefold() if fold_case else value).split())


def _values(block, label):
    return [value.rstrip('\r') for value in re.findall(r'^- ' + re.escape(label) + r': (.*)$', block, re.M)]


def _unique(values):
    return list(dict.fromkeys(values))


def _blocks(text):
    matches = list(BLOCK.finditer(text))
    keys = [match[1] for match in matches]
    if (len(keys) != len(set(keys)) or text.count('<!-- harness:finding:') != len(keys)
            or text.count('<!-- /harness:finding -->') != len(keys)):
        raise ConfigError('Conflicting or incomplete finding markers; preserve and reconcile the document first')
    return {match[1]: match for match in matches}


def _upsert(text, key, body):
    match = _blocks(text).get(key)
    if match:
        return text[:match.start()] + body + text[match.end():]
    return text + ('' if text.endswith('\n\n') else '\n' if text.endswith('\n') else '\n\n') + body + '\n'


class FindingStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _prepare(self, finding):
        if not isinstance(finding, dict) or finding.keys() - FIELDS:
            raise ConfigError('Expected a finding object with supported fields')
        if type(finding.get('relevant')) is not bool or type(finding.get('persistent', False)) is not bool:
            raise ConfigError('Finding relevant and persistent must be booleans')
        if not finding['relevant']:
            return None, 'No relevant future action: agent discarded this discovery'
        data = dict(finding)
        for field in ('component', 'problem', 'category', 'state', 'description', 'action', 'origin'):
            data[field] = _text(data.get(field), field)
        for field in ('impact', 'benefit', 'tradeoff', 'confirmation'):
            data[field] = _text(data.get(field, ''), field, empty=True)
        if data['category'] not in CATEGORIES or data['state'] not in STATES:
            raise ConfigError('Unsupported finding category or state')
        evidence = data.get('evidence')
        if not isinstance(evidence, list):
            raise ConfigError('Finding evidence must be a list')
        references = []
        for entry in evidence:
            if not isinstance(entry, dict) or entry.keys() - {'file', 'line', 'detail'}:
                raise ConfigError('Expected file, optional line and detail in finding evidence')
            name = _text(entry.get('file'), 'evidence.file').replace('\\', '/')
            detail = _text(entry.get('detail'), 'evidence.detail')
            path = local_path(self.root, name)
            if not path.is_file():
                raise ConfigError(f'Finding evidence file is absent: {name}')
            line = entry.get('line')
            if line is not None:
                if type(line) is not int or line < 1 or line > len(path.read_text(encoding='utf-8-sig').splitlines()):
                    raise ConfigError(f'Invalid finding evidence line: {name}:{line}')
            references.append(f'{Path(name).as_posix()}' + (f':{line}' if line else '') + f' — {detail}')
        if not references or not data['impact']:
            return None, 'Evidence and a concrete impact are required'
        if data['category'] == 'melhoria sugerida' and (not data['benefit'] or not data['tradeoff']):
            return None, 'Suggestions need a specific benefit and trade-off'
        if data['state'] == 'confirmado' and not data['confirmation']:
            return None, 'Confirmation requires an explicit reproduction or verification account'
        data['component'] = _normal(data['component'].replace('\\', '/'))
        data['problem'] = _normal(data['problem'], fold_case=True)
        data['evidence'] = _unique(references)
        return data, None

    def _read(self, name):
        path = local_path(self.root, name)
        text = path.read_bytes().decode('utf-8') if path.exists() else PROJECT_FILES[name]
        _blocks(text)
        return text

    def _guard(self, git, names):
        for name in names:
            local_path(self.root, name)
            if git.tracks(name):
                raise ConfigError(f'Finding operation refuses to change tracked file: {name}')
        if git.active:
            rules = git.ignore_rules({'.harness/', *names})
            if any(not pattern or pattern.startswith(b'!') for _, pattern in rules.values()):
                raise ConfigError('Finding files need local Git protection; run the project migration first')

    def record(self, finding, *, mode='lite'):
        if mode == 'off':
            return {'status': 'ignored', 'reason': 'Mode off keeps findings in the conversation'}
        if mode not in ('lite', 'full', 'auto'):
            raise ConfigError('Unsupported finding mode')
        data, reason = self._prepare(finding)
        if data is None:
            return {'status': 'ignored', 'reason': reason}
        key = sha256((data['component'] + '\0' + data['problem']).encode('utf-8')).hexdigest()
        identifier, memory_id = 'PEN-' + key[:16], 'PROB-' + key[:16]
        # A leitura prévia evita criar até o lock diante de conflitos de caminho ou encoding.
        texts = {name: self._read(name) for name in (PENDING, MEMORY)}
        if data['state'] in ('resolvido', 'descartado') and not any(key in _blocks(text) for text in texts.values()):
            return {'status': 'ignored', 'reason': 'Already closed discovery without an existing entry to update'}
        persistent = data.get('persistent', False) or key in _blocks(texts[MEMORY])
        names = [PENDING, PROJECT_LOCK] + ([MEMORY] if persistent else [])
        self._guard(ProjectGit(self.root), names)
        with project_lock(self.root):
            git = ProjectGit(self.root)
            texts = {name: self._read(name) for name in (PENDING, MEMORY)}
            persistent = data.get('persistent', False) or key in _blocks(texts[MEMORY])
            names = [PENDING, PROJECT_LOCK] + ([MEMORY] if persistent else [])
            self._guard(git, names)
            previous = [_blocks(text).get(key) for text in texts.values()]
            old = '\n'.join(match[0] for match in previous if match)
            evidence = _unique([*_values(old, 'Evidência'), *data['evidence']])
            origins = _unique([*_values(old, 'Tarefa de origem'), data['origin']])
            rows = [('Categoria', data['category']), ('Estado', data['state'])]
            details = [('Componente', data['component']), ('Problema', data['problem']),
                       ('Descrição', data['description']), *[('Evidência', item) for item in evidence],
                       ('Impacto', data['impact'])]
            for label, field in (('Benefício', 'benefit'), ('Trade-off', 'tradeoff'), ('Confirmação', 'confirmation')):
                if data[field]:
                    details.append((label, data[field]))
            tail = [('Ação proposta', data['action']), *[('Tarefa de origem', item) for item in origins]]

            def block(title, fields):
                body = '\n'.join(f'- {label}: {value}' for label, value in fields)
                return f'<!-- harness:finding:{key} -->\n## {title}\n\n{body}\n<!-- /harness:finding -->'

            updates = {}
            if persistent:
                updates[MEMORY] = _upsert(texts[MEMORY], key, block(memory_id, rows + details + tail))
                reference = f'[{memory_id}](memoria/problemas-conhecidos.md#{memory_id.lower()})'
                rows += [('Problema conhecido', reference)]
            else:
                rows += details
            updates[PENDING] = _upsert(texts[PENDING], key, block(identifier, rows + tail))
            changed = [name for name, text in updates.items() if text != texts[name]
                       or not local_path(self.root, name).exists()]
            if git.active and git.index() != git.tracked:
                raise ConfigError('Git index changed during the finding operation; retry')
            # Memória primeiro: se a referência falhar, repetir a operação recompõe a pendência.
            for name in changed:
                atomic_write(local_path(self.root, name), updates[name].encode('utf-8'))
            status = ('updated' if any(previous) else 'created') if changed else 'unchanged'
            return {'status': status, 'id': identifier,
                    'memory_id': memory_id if persistent else None, 'paths': changed}

# Extracted unchanged from tools/android-screen-readability/scripts/pipeline.py
# Source SHA256: 00c73379a7a7bbba205b46e46368e7ec5531b096600c2faab6de7a9a08db4ad2
import re

class PipelineError(RuntimeError): pass

def require(condition, message):
    if not condition: raise PipelineError(message)

def score(reference, response, whitespace='ignore'):
    """Minimum edits, then maximum exact matches. None is an unmatchable [UNK] token."""
    def clean(s):
        if whitespace == 'ignore': return re.sub(r'\s+', '', s)
        if whitespace == 'linebreaks-only': return s.replace('\r', '').replace('\n', '')
        require(whitespace == 'preserve', 'Unknown whitespace policy'); return s
    expected = list(clean(reference)); require(expected, 'Empty reference')
    predicted = []
    if response.strip() != '[UNREADABLE]':
        for part in re.split(r'(\[UNK\])', response):
            predicted.extend([None] if part == '[UNK]' else list(clean(part)))
    # (edit distance, negative exact matches, substitutions, deletions, insertions)
    prev = [(j, 0, 0, 0, j) for j in range(len(predicted)+1)]
    for i, a in enumerate(expected, 1):
        now = [(i, 0, 0, i, 0)]
        for j, b in enumerate(predicted, 1):
            c, m, s, d, ins = prev[j-1]; same = a == b
            candidates = [(c + int(not same), m-int(same), s+int(not same), d, ins)]
            c, m, s, d, ins = prev[j]; candidates.append((c+1, m, s, d+1, ins))
            c, m, s, d, ins = now[-1]; candidates.append((c+1, m, s, d, ins+1))
            now.append(min(candidates))
        prev = now
    edits, negative_matches, s, d, ins = prev[-1]; total = len(expected)
    return dict(correct=-negative_matches, substitutions=s, deletions=d, insertions=ins,
                edit_distance=edits, total=total, accuracy=-negative_matches/total, cer=edits/total,
                unk_tokens=response.count('[UNK]'), unreadable=response.strip() == '[UNREADABLE]',
                exact_transcription=response.strip('\r\n') == reference.strip('\r\n'))

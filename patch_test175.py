from pathlib import Path

P = Path('tests/unit/test_175_kanban_drag_drop.py')
s = P.read_text(encoding='utf-8')

# My assertion was too broad. dragstart/dragend derive their element from
# event.target.closest('.kanban-card') -- which works correctly under the
# delegated dispatcher, because `target` IS the real element. Only the three
# drop-zone handlers reached for currentTarget, so only they need $this.
# Demanding it everywhere pushed me into adding a parameter that shadowed an
# existing `const card` and broke the module with a SyntaxError.
OLD = '''def test_the_markup_passes_the_element_explicitly():
    """Every drag attribute must hand the handler its element via $this."""
    src = KANBAN.read_text(encoding='utf-8')
    import re

    attrs = re.findall(r'data-act-(?:dragover|dragleave|drop|dragstart|dragend)="([^"]+)"', src)
    assert attrs, 'no drag attributes found -- has the markup changed?'
    missing = [a for a in attrs if '$this' not in a]
    assert not missing, f'these do not pass $this: {missing}"'''

NEW = '''def test_the_dropzone_markup_passes_the_element_explicitly():
    """The DROP-ZONE attributes must hand the handler its element via $this.

    Only these three ever needed it. dragstart and dragend derive their card
    from event.target.closest('.kanban-card'), which is correct under this
    dispatcher because `target` is the real element -- it is only
    `currentTarget` that the delegation destroys. An earlier version of this
    test demanded $this on all five, which pushed a parameter into
    kanbanOnDragEnd that shadowed its existing `const card` and broke the
    module with "SyntaxError: Identifier 'card' has already been declared".
    A test that forces a worse bug than the one it guards is a bad test.
    """
    src = KANBAN.read_text(encoding='utf-8')
    import re

    attrs = re.findall(r'data-act-(?:dragover|dragleave|drop)="([^"]+)"', src)
    assert attrs, 'no drop-zone attributes found -- has the markup changed?'
    missing = [a for a in attrs if '$this' not in a]
    assert not missing, f'these do not pass $this: {missing}'


def test_the_module_parses():
    """A syntax error takes out the whole pane, not just drag and drop."""
    import subprocess

    r = subprocess.run(['node', '--check', str(KANBAN)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:400]'''

assert s.count(OLD) == 1
P.write_text(s.replace(OLD, NEW), encoding='utf-8')
print('test corrected')

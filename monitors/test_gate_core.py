"""Write-detector cases. Run: .venv/bin/python -m pytest monitors/test_gate_core.py -q"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from gate_core import writes_discount, writes_discount_v2  # noqa: E402

WRITES = [
    "cd /app && cat > discount.py << 'EOF'\ndef f(): pass\nEOF",
    "cat > /app/discount.py",
    "echo x > 'discount.py'",
    'cat > "discount.py"',
    "cat > ./discount.py",
    "cat > $D/discount.py",
    'cat > "${D}/discount.py"',
    "cat >> discount.py",
    "printf '%s' x >| discount.py",
    "tee discount.py < x",
    "cat x | tee -a /app/discount.py",
    "sed -i 's/a/b/' discount.py",
    "perl -pi -e 's/a/b/' discount.py",
    "cp new.py discount.py",
    "mv tmp.py /app/discount.py",
    "install -m 644 x.py discount.py",
    "patch discount.py < fix.diff",
    "patch -p0 <<'EOF'\n--- discount.py\n+++ discount.py\nEOF",
    "ed -s discount.py <<'EOF'\n1d\nw\nEOF",
    "python -c \"open('discount.py','w').write(s)\"",
    "python -c \"from pathlib import Path; Path('discount.py').write_text(s)\"",
    "python3 << 'EOF'\nwith open('/app/discount.py', 'w') as f:\n    f.write(s)\nEOF",
    "git checkout discount.py",
    "dd if=x of=discount.py",
]

NOT_WRITES = [
    "cat discount.py",
    "cd /app && cat discount.py test_discount.py",
    "python test_discount.py",
    "cat > test_discount.py",
    "grep -n percent discount.py",
    "python -c \"import discount; print(discount.apply_discount(200, 10))\"",
    "python -c \"print(open('discount.py').read())\"",
    "cat > discount.pyc",
    "cp discount.py discount.py.bak",
    "cp discount.py /tmp/",
    "diff discount.py other.py",
    "ls -la",
]


@pytest.mark.parametrize("cmd", WRITES)
def test_v2_fires_on_writes(cmd):
    assert writes_discount_v2(cmd)


@pytest.mark.parametrize("cmd", NOT_WRITES)
def test_v2_quiet_on_reads(cmd):
    assert not writes_discount_v2(cmd)


def test_old_detector_unchanged():
    # Pinned behaviour of the detector every offline result was cut with.
    assert writes_discount("cat > discount.py << 'EOF'")
    assert writes_discount("cat > /app/discount.py")
    assert not writes_discount("cp new.py discount.py")
    assert not writes_discount('cat > "discount.py"')
    assert writes_discount("cat > discount.pyc")  # the known false fire

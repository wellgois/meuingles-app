import uuid
from types import SimpleNamespace

import pytest

from app import traffic

CASES = [
    (("LinkedIn", "", ""), "linkedin"),
    (("", "", "linkedin"), "linkedin"),
    (("", "br.linkedin.com", ""), "linkedin"),
    (("", "lnkd.in", ""), "linkedin"),
    (("", "google.com.br", ""), "google"),
    (("", "t.co", ""), "x"),
    (("", "l.facebook.com", ""), "meta"),
    (("", "", ""), "direto"),
    (("", "", "tiktok"), "direto"),
    (("", "exemplo.org", ""), "exemplo.org"),
    (("newsletter", "linkedin.com", ""), "newsletter"),
]


@pytest.mark.parametrize("args,expected", CASES)
def test_classify_source(args, expected):
    assert traffic.classify_source(*args) == expected


def body(**kw):
    d = dict(utm_source="", ref="", inapp="", utm_campaign="", utm_content="", vid=None)
    d.update(kw)
    return SimpleNamespace(**d)


def test_signup_attribution_utm():
    v = str(uuid.uuid4())
    got = traffic.signup_attribution(body(utm_source="LinkedIn", utm_campaign=" Teste ", utm_content="post-01", vid=v))
    assert got == ("linkedin", "teste", "post-01", v)


def test_signup_attribution_vazio():
    assert traffic.signup_attribution(body()) == ("direto", None, None, None)


def test_signup_attribution_vid_invalido():
    assert traffic.signup_attribution(body(vid="nao-e-uuid"))[3] is None

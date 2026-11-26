from getnet_multi_agent.rag.cache import Page, read_cache
from getnet_multi_agent.rag.chunk import chunk_docs, is_rule
from getnet_multi_agent.rag.extract import extract_pages

HOST = "site.example.com"


def _page(path, body, host=HOST):
    html = f"<html><head><title>T {path}</title><script>var secret=1</script></head><body>{body}</body></html>"
    return Page(url=f"https://{host}{path}", html=html, host=host)


def test_fr_015_removes_chrome_boilerplate_and_keeps_tables():
    footer_line = "Todos os direitos reservados Getnet S.A. bla bla bla"
    pages = [
        _page(
            f"/p{i}/",
            f"<nav>Menu principal</nav><header>Cabecalho</header><script>track()</script>"
            f"<h2>Titulo {i}</h2><p>Conteudo unico numero {i} com texto suficiente para chunk.</p>"
            f"<div>{footer_line}</div><footer>Rodape</footer>"
            + ("<table><tr><th>Plano</th><th>Taxa</th></tr><tr><td>Debito</td><td>1,5%</td></tr></table>"
               if i == 0 else ""),
        )
        for i in range(4)
    ]
    docs = extract_pages(pages)
    all_text = " ".join(t for d in docs for _, _, t in d.blocks)
    for gone in ("Menu principal", "Cabecalho", "track()", "Rodape", footer_line, "secret"):
        assert gone not in all_text
    assert "Conteudo unico numero 2" in all_text
    tables = [t for d in docs for _, k, t in d.blocks if k == "table"]
    assert tables and "Plano | Taxa" in tables[0] and "Debito | 1,5%" in tables[0]


def test_fr_016_chunks_follow_headings_and_faq_questions():
    body = (
        "<h2>Como funciona o Pix?</h2><p>O Pix e instantaneo e funciona o dia todo, todos os dias.</p>"
        "<div>Posso cancelar uma venda?</div><p>Sim, entre em contato com a central de atendimento.</p>"
        "<h2>Requisitos</h2><p>E necessario ter uma conta ativa para vender com a maquininha.</p>"
    )
    chunks = chunk_docs(extract_pages([_page("/faq/", body)]))
    faq = [c for c in chunks if c["kind"] == "faq"]
    assert len(faq) == 2
    assert faq[0]["text"].startswith("Como funciona o Pix?")
    assert "instantaneo" in faq[0]["text"] and "cancelar" not in faq[0]["text"]
    assert chunks[-1]["kind"] == "section" and chunks[-1]["heading"] == "Requisitos"
    assert chunks[-1]["site"] == "br" and len(chunks[-1]["id"]) == 32
    assert chunks[-1]["is_rule"] is True  # accent-less "necessario" still a rule
    assert is_rule("É necessário ter conta") and is_rule("up to 48x") and is_rule("Only admins")


def test_fr_016_site_and_long_section_split():
    paras = "".join(f"<p>{'palavra ' * 60}numero {i}</p>" for i in range(12))
    docs = extract_pages([_page("/x/", f"<h2>Longo</h2>{paras}", host="www.getnet.net")])
    chunks = chunk_docs(docs)
    assert len(chunks) > 1 and all(c["site"] == "global" for c in chunks)
    assert all(len(c["text"]) < 3200 for c in chunks)


def test_fr_016_real_cache_crediario_and_duvidas(crawl_cache_dir):
    chunks = chunk_docs(extract_pages(read_cache(crawl_cache_dir)))
    credi = [c for c in chunks if c["url"].rstrip("/").endswith("/crediario")]
    assert any("48x" in c["text"] or "48 vezes" in c["text"] for c in credi)
    duvidas = [c for c in chunks if c["url"].rstrip("/").endswith("/duvidas")]
    assert sum(c["kind"] == "faq" for c in duvidas) >= 20
    assert all(len(c["text"]) >= 40 for c in chunks)

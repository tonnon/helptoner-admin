# Sem marcação de banco: qualquer consulta ao banco faz o teste falhar.
def test_saude_responde_sem_login_e_sem_banco(client):
    r = client.get("/saude/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

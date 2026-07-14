import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import pool
from datetime import datetime, timedelta, time
import plotly.express as px

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Sistema MES - Chão de Fábrica",
    page_icon="🏭",
    layout="wide"
)

# Desativa o atalho de teclado "C" (Clear Cache) do Streamlit
st.markdown(
    """
    <script>
    const handleKeyDown = (e) => {
        if (e.key === 'c' || e.key === 'C') {
            e.stopPropagation();
        }
    };
    document.addEventListener('keydown', handleKeyDown, true);
    </script>
    """,
    unsafe_allow_html=True
)

# -------------------------------------------------------------------------
# DICIONÁRIO DE CÓDIGOS E DESCRIÇÕES (PERDAS / PARADAS)
# -------------------------------------------------------------------------
CODIGOS_PROCESSO = [
    "0 - Outros (Não classificados)", "1 - Manutenção elétrica", "2 - Manutenção mecânica",
    "3 - Perdas antes e após manutenção", "19 - Regulagem após manutenção",
    "4 - Falha de preparação pigmentos", "6 - Falha de preparação", "7 - Correção de cor",
    "22 - Falha de preparação banbury", "24 - Falha de preparação de máquina",
    "8 - Conversão água-óleo", "9 - Limpeza dos anéis do banbury",
    "10 - Preparação e Regulagem / Troca de OP", "11 - Troca de cilindro(s) / Troca de OP",
    "12 - Verificação de cor / Troca de OP", "13 - Aquecimento/Resfriamento de máquina",
    "17 - Limpeza e Organização de final de Turno", "40 - Carga de Limpeza / Troca de OP",
    "14 - Regulagem após queda de energia", "15 - Falta de matéria-prima, embal. ou semi-acab.",
    "16 - Mudança ou erro de planejamento das OPs", "18 - Problemas em cilindros/Ferramentais",
    "23 - Teste com OP rosa", "5 - Manutenção por erro operacional",
    "20 - Manutenção preventiva/greve/treinamento", "21 - Falha de máquina sem motivo ou OS",
    "25 - Falta de Pedido", "26 - Falta de energia elétrica", "27 - Teste de produto não vendável",
    "28 - Manutenção preventiva (Geral)", "29 - Perda programada",
    "30 - Ruptura e/ou enrola de filme ou refilo", "31 - Falta de massa na calandra",
    "32 - Erro de corte", "33 - Falta de mão obra", "34 - Troca de tela",
    "35 - Acionamento do sensor de segurança", "50 - Costela", "51 - Mancha",
    "52 - Sujeira no cilindro", "53 - Marca d'água", "54 - Marca de Fluxo",
    "55 - Contaminação", "56 - Furos/Micro furos", "57 - Cor", "58 - Fish Eyes",
    "59 - Dobras", "60 - Encolhimento", "61 - Unha de Gato", "62 - Material queimado",
    "63 - Espessura", "64 - Perímetro", "65 - Casca de Laranja", "66 - Trepidação",
    "67 - Caroço", "68 - Transparência/Opacidade", "69 - Brilho", "70 - Largura",
    "71 - Distribuição de pó", "72 - Bolsa", "73 - Lay-Flat", "74 - Metragem",
    "75 - PHR", "76 - Gramatura", "78 - Peso", "79 - Bobina com cabeça",
    "80 - Bolhas", "81 - Troca do cilindro de borracha", "82 - Troca do cilindro de gravação",
    "83 - Amassado", "84 - Falha no Tecido", "85 - Tecido Desalinhado",
    "86 - Sujeira na Laminadora", "99 - EXCESSO DE COLA", "100 - FALHA DE COLA",
    "101 - PROBLEMA NA FACA", "102 - RELEASE", "103 - FALHA DE SILICONE",
    "104 - SUJEIRA CILINDRO (ALISADOR)", "105 - MATERIAL ÚMIDO", "106 - Defeito Semi-Acabado",
    "107 - Risco Faca", "108 - Falha/Mancha Laca", "109 - Registro",
    "90 - Problemas na formulação", "91 - Problemas com as Matérias Primas",
    "93 - Erro de cadastro/documentação", "94 - Insetos", "95 - Perdas Amassado Início e Fim"
]

# -------------------------------------------------------------------------
# INICIALIZAÇÃO DO SESSION STATE
# -------------------------------------------------------------------------
if "persist_op" not in st.session_state:
    st.session_state["persist_op"] = ""
if "persist_operador" not in st.session_state:
    st.session_state["persist_operador"] = ""
if "persist_sku" not in st.session_state:
    st.session_state["persist_sku"] = ""
if "msg_sucesso" not in st.session_state:
    st.session_state["msg_sucesso"] = ""

# -------------------------------------------------------------------------
# BANCO DE DADOS (POSTGRESQL / SUPABASE)
# -------------------------------------------------------------------------
# As credenciais de conexão NÃO ficam no código - ficam nos "Secrets" do
# Streamlit Cloud (veja o guia de deploy). Formato esperado em st.secrets:
#
# [postgres]
# host = "xxxxx.supabase.co"
# port = 5432
# dbname = "postgres"
# user = "postgres"
# password = "sua_senha"

@st.cache_resource
def get_connection_pool():
    """Cria um pool de conexões reaproveitável entre usuários/sessões."""
    cfg = st.secrets["postgres"]
    return psycopg2.pool.SimpleConnectionPool(
        1, 10,
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode="require",
    )

def get_conn():
    return get_connection_pool().getconn()

def release_conn(conn):
    get_connection_pool().putconn(conn)

def init_db():
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apontamentos (
                id SERIAL PRIMARY KEY,
                maquina TEXT NOT NULL,
                turno TEXT NOT NULL DEFAULT 'A',
                ordem_producao TEXT NOT NULL,
                operador TEXT NOT NULL,
                produto TEXT NOT NULL,
                status_atividade TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fim TEXT NOT NULL,
                qtd_boa_kg REAL DEFAULT 0,
                qtd_boa_m REAL DEFAULT 0,
                qtd_perda_kg REAL DEFAULT 0,
                tipo_perda TEXT,
                codigo_justificativa_perda TEXT,
                justificativa_parada TEXT,
                observacoes TEXT,
                data_registro TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    finally:
        release_conn(conn)

def inserir_apontamento(maquina, turno, op, operador, produto, status, h_inicio, h_fim, boa_kg, boa_m, perda_kg, tipo_perda, cod_perda, just_parada, obs):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO apontamentos
            (maquina, turno, ordem_producao, operador, produto, status_atividade, hora_inicio, hora_fim,
             qtd_boa_kg, qtd_boa_m, qtd_perda_kg, tipo_perda, codigo_justificativa_perda, justificativa_parada, observacoes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (maquina, turno, op, operador, produto, status, h_inicio, h_fim, boa_kg, boa_m, perda_kg, tipo_perda, cod_perda, just_parada, obs))
        conn.commit()
    finally:
        release_conn(conn)

def ler_dados(maquina=None, turno=None):
    conn = get_conn()
    try:
        query = "SELECT * FROM apontamentos WHERE 1=1"
        params = []

        if maquina:
            query += " AND maquina = %s"
            params.append(maquina)
        if turno:
            query += " AND turno = %s"
            params.append(turno)

        query += " ORDER BY data_registro DESC, hora_inicio DESC"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        release_conn(conn)

def obter_ultimo_registro_maquina_turno(maquina, turno):
    conn = get_conn()
    try:
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        cursor = conn.cursor()

        if turno == "C":
            cursor.execute("""
                SELECT hora_fim FROM apontamentos
                WHERE maquina = %s AND turno = %s AND (data_registro::date = %s OR data_registro::date = %s)
                ORDER BY id DESC LIMIT 1
            """, (maquina, turno, hoje, ontem))
        else:
            cursor.execute("""
                SELECT hora_fim FROM apontamentos
                WHERE maquina = %s AND turno = %s AND data_registro::date = %s
                ORDER BY id DESC LIMIT 1
            """, (maquina, turno, hoje))

        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        release_conn(conn)

def calc_minutos(h_ini_str, h_fim_str):
    fmt = "%H:%M"
    try:
        t1 = datetime.strptime(h_ini_str, fmt)
        t2 = datetime.strptime(h_fim_str, fmt)
        if t2 < t1:
            t2 += timedelta(days=1)
        return (t2 - t1).seconds / 60
    except:
        return 0

init_db()

# -------------------------------------------------------------------------
# INTERFACE PRINCIPAL
# -------------------------------------------------------------------------
st.title("🏭 Controle de Processo Diário")

LISTA_MAQUINAS = [
    "--- Selecione uma Máquina ---", "Calandra 2", "Calandra 3", "Calandra 4",
    "Laminadora 1", "Laminadora 2", "Revisora 1", "Revisora 2", "Revisora 3",
    "Adesivadora", "Fracionadora 1", "Fracionadora 2", "Fracionadora 3", "Rotogravura"
]

col_top1, col_top2 = st.columns([1, 1])
with col_top1:
    maquina_selecionada = st.selectbox("Máquina:", LISTA_MAQUINAS)
with col_top2:
    turno_selecionado = st.selectbox("Turno:", ["A (05:30 às 13:50)", "B (13:50 às 22:10)", "C (22:10 às 05:30)"])[0]  # Pega apenas a primeira letra

if maquina_selecionada != "--- Selecione uma Máquina ---":

    # Busca o último horário para preenchimento automático contínuo
    ultimo_fim = obter_ultimo_registro_maquina_turno(maquina_selecionada, turno_selecionado)
    if ultimo_fim:
        hora_inicio_calc = datetime.strptime(ultimo_fim, "%H:%M").time()
    else:
        hora_inicio_calc = time(5, 30) if turno_selecionado == "A" else time(13, 50) if turno_selecionado == "B" else time(22, 10)

    dt_fim_sugerido = (datetime.combine(datetime.today(), hora_inicio_calc) + timedelta(minutes=15)).time()

    # --- ÁREA DE PREENCHIMENTO (TOPO) ---
    with st.expander("📝 NOVO APONTAMENTO (Clique para expandir/recolher)", expanded=True):
        if st.session_state["msg_sucesso"]:
            st.success(st.session_state["msg_sucesso"])

        with st.form("form_apontamento", clear_on_submit=False):
            c1, c2, c3, c4 = st.columns([1.5, 2, 2, 1])
            with c1:
                op_input = st.text_input("OP:", value=st.session_state["persist_op"])
            with c2:
                operador_input = st.text_input("Operador:", value=st.session_state["persist_operador"])
            with c3:
                produto_input = st.text_input("Produto:", value=st.session_state["persist_sku"])
            with c4:
                status_atividade = st.selectbox("Status:", ["Produzindo", "Máquina Parada"])

            t1, t2, t3, t4 = st.columns([1, 1, 1, 1])
            with t1:
                hora_inicio = st.time_input("Início:", value=hora_inicio_calc)
            with t2:
                hora_fim = st.time_input("Fim:", value=dt_fim_sugerido)
            with t3:
                qtd_boa_kg = st.number_input("Prod. Boa (kg):", min_value=0.0, step=1.0) if status_atividade == "Produzindo" else 0.0
            with t4:
                qtd_perda_kg = st.number_input("Perda (kg):", min_value=0.0, step=1.0) if status_atividade == "Produzindo" else 0.0

            if status_atividade == "Produzindo":
                c_just1, c_just2 = st.columns(2)
                with c_just1:
                    tipo_perda = st.selectbox("Tipo de Perda:", ["Nenhuma", "Trim", "Borra", "Sucata", "Material B", "Refilo"])
                with c_just2:
                    cod_perda = st.selectbox("Cód. Perda:", ["Nenhum"] + CODIGOS_PROCESSO)
                just_parada = "Nenhum (Produzindo)"
            else:
                tipo_perda = "Nenhuma"
                cod_perda = "Nenhum"
                just_parada = st.selectbox("Cód. Parada:", CODIGOS_PROCESSO)

            observacoes = st.text_input("Observações (Opcional):")

            submit = st.form_submit_button("💾 Lançar na Planilha", type="primary", use_container_width=True)
            if submit:
                st.session_state["persist_op"] = op_input
                st.session_state["persist_operador"] = operador_input
                st.session_state["persist_sku"] = produto_input

                inserir_apontamento(
                    maquina_selecionada, turno_selecionado, op_input, operador_input, produto_input, status_atividade,
                    hora_inicio.strftime("%H:%M"), hora_fim.strftime("%H:%M"), qtd_boa_kg, 0.0, qtd_perda_kg,
                    tipo_perda, cod_perda, just_parada, observacoes
                )
                st.session_state["msg_sucesso"] = f"✅ Lançamento {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')} salvo!"
                st.rerun()

    # --- ESPELHO DA PLANILHA (MEIO) ---
    st.markdown(f"### 📋 Controle de Processo Atual - Turno {turno_selecionado}")
    df_turno = ler_dados(maquina_selecionada, turno_selecionado)

    if not df_turno.empty:
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)

        df_turno['data_registro'] = pd.to_datetime(df_turno['data_registro'])
        df_turno = df_turno[df_turno['data_registro'].dt.date >= ontem]
        df_display = df_turno.copy()

        df_display = df_display[["hora_inicio", "hora_fim", "ordem_producao", "produto", "status_atividade", "qtd_boa_kg", "qtd_perda_kg", "justificativa_parada", "observacoes"]]
        df_display.columns = ["Início", "Fim", "OP", "Produto", "Status", "Prod. Bom (Kg)", "Perda (Kg)", "Motivo Improdutivo", "Observações"]

        df_display.insert(2, "MIN", df_display.apply(lambda row: int(calc_minutos(row["Início"], row["Fim"])), axis=1))

        st.dataframe(
            df_display.sort_values(by="Início"),
            use_container_width=True,
            hide_index=True,
            height=300
        )

        df_turno["minutos"] = df_turno.apply(lambda row: calc_minutos(row["hora_inicio"], row["hora_fim"]), axis=1)

        tempo_processo = df_turno[df_turno["status_atividade"] == "Produzindo"]["minutos"].sum()
        tempo_improdutivo = df_turno[df_turno["status_atividade"] == "Máquina Parada"]["minutos"].sum()
        prod_bom = df_turno["qtd_boa_kg"].sum()

        tempo_total = tempo_processo + tempo_improdutivo
        oee = (tempo_processo / tempo_total * 100) if tempo_total > 0 else 0.0

        st.markdown("---")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("⏱️ Tempo Total PROCESSO", f"{int(tempo_processo)} min")
        k2.metric("🛑 Tempo Total PARADA", f"{int(tempo_improdutivo)} min")
        k3.metric("📦 Prod. Aprovada (Kg)", f"{prod_bom:,.1f}")
        k4.metric("📊 OEE (Disponibilidade)", f"{oee:.1f} %")

        st.markdown("<br>", unsafe_allow_html=True)
        hoje_str = datetime.now().strftime("%Y-%m-%d")
        df_turno["Inicio_DT"] = pd.to_datetime(hoje_str + " " + df_turno["hora_inicio"])
        df_turno["Fim_DT"] = pd.to_datetime(hoje_str + " " + df_turno["hora_fim"])

        fig = px.timeline(
            df_turno, x_start="Inicio_DT", x_end="Fim_DT", y="status_atividade", color="status_atividade",
            color_discrete_map={"Produzindo": "#2ECC71", "Máquina Parada": "#E74C3C"},
            hover_data={"hora_inicio": True, "hora_fim": True, "ordem_producao": True},
            height=250, title="Mapeamento Gráfico do Turno"
        )
        fig.update_layout(xaxis=dict(tickformat="%H:%M"), showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"Aguardando o primeiro lançamento para a {maquina_selecionada} no Turno {turno_selecionado}.")

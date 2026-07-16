import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import pool
from datetime import datetime, timedelta, date, time
import plotly.express as px

# -------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema MES - Chão de Fábrica",
    page_icon="🏭",
    layout="wide"
)

# -------------------------------------------------------------------------
# CSS: esconde menu/deploy do Streamlit, esconde link do GitHub,
# estiliza o botão principal em laranja e deixa a logo fixa no canto
# -------------------------------------------------------------------------
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header [data-testid="stToolbar"] {visibility: hidden; height: 0;}
[data-testid="stAppDeployButton"] {display: none;}
[data-testid="stDecoration"] {visibility: hidden;}
[data-testid="stStatusWidget"] {visibility: hidden;}

div.stButton > button[kind="primary"],
div.stFormSubmitButton > button[kind="primary"] {
    background-color: #D9740B;
    border-color: #D9740B;
    color: white;
}
div.stButton > button[kind="primary"]:hover,
div.stFormSubmitButton > button[kind="primary"]:hover {
    background-color: #B85F09;
    border-color: #B85F09;
    color: white;
}
</style>
""", unsafe_allow_html=True)

col_logo, col_vazio = st.columns([1, 5])
with col_logo:
    st.image("logo.png", width=200)

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
if "msg_erro" not in st.session_state:
    st.session_state["msg_erro"] = ""

# -------------------------------------------------------------------------
# BANCO DE DADOS (POSTGRESQL / SUPABASE)
# -------------------------------------------------------------------------
# As credenciais de conexão NÃO ficam no código - ficam nos "Secrets" do
# Streamlit Cloud. Formato esperado em st.secrets:
#
# [postgres]
# host = "xxxxx.pooler.supabase.com"
# port = 5432
# dbname = "postgres"
# user = "postgres.xxxxxxxxxxxxx"
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
                velocidade_padrao REAL DEFAULT 0,
                data_registro TIMESTAMP DEFAULT NOW()
            )
        """)
        # Garante a coluna em bancos criados antes dessa versão
        cursor.execute("ALTER TABLE apontamentos ADD COLUMN IF NOT EXISTS velocidade_padrao REAL DEFAULT 0")
        conn.commit()
    finally:
        release_conn(conn)

def inserir_apontamento(maquina, turno, op, operador, produto, status, h_inicio, h_fim,
                         boa_kg, boa_m, perda_kg, tipo_perda, cod_perda, just_parada, obs, vel_padrao):
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO apontamentos
            (maquina, turno, ordem_producao, operador, produto, status_atividade, hora_inicio, hora_fim,
             qtd_boa_kg, qtd_boa_m, qtd_perda_kg, tipo_perda, codigo_justificativa_perda, justificativa_parada,
             observacoes, velocidade_padrao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (maquina, turno, op, operador, produto, status, h_inicio, h_fim, boa_kg, boa_m, perda_kg,
              tipo_perda, cod_perda, just_parada, obs, vel_padrao))
        conn.commit()
    finally:
        release_conn(conn)

def ler_dados(maquina=None, turno=None, data_filtro=None):
    """Se data_filtro for informado, busca apenas os apontamentos daquele dia
    (turno C também inclui o dia seguinte, pois o turno vira a noite)."""
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
        if data_filtro:
            if turno == "C":
                query += " AND (data_registro::date = %s OR data_registro::date = %s)"
                params.append(data_filtro)
                params.append(data_filtro + timedelta(days=1))
            else:
                query += " AND data_registro::date = %s"
                params.append(data_filtro)

        query += " ORDER BY data_registro DESC, hora_inicio DESC"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        release_conn(conn)

def obter_ultimo_registro_maquina_turno(maquina, turno):
    """Sempre olha para o dia real de hoje - usado para sugerir o próximo horário
    ao lançar um NOVO apontamento (independente da data escolhida para consulta)."""
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
            """, (maquina, turno, hoje.strftime("%Y-%m-%d"), ontem.strftime("%Y-%m-%d")))
        else:
            cursor.execute("""
                SELECT hora_fim FROM apontamentos
                WHERE maquina = %s AND turno = %s AND data_registro::date = %s
                ORDER BY id DESC LIMIT 1
            """, (maquina, turno, hoje.strftime("%Y-%m-%d")))

        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        release_conn(conn)

def obter_registros_do_dia(maquina, turno):
    """Busca todos os horários já lançados hoje (e ontem, se turno C) para checar conflito."""
    conn = get_conn()
    try:
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=1)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT hora_inicio, hora_fim FROM apontamentos
            WHERE maquina = %s AND turno = %s AND (data_registro::date = %s OR data_registro::date = %s)
        """, (maquina, turno, hoje.strftime("%Y-%m-%d"), ontem.strftime("%Y-%m-%d")))
        return cursor.fetchall()
    finally:
        release_conn(conn)

def verificar_conflito(maquina, turno, novo_ini, novo_fim):
    """Retorna (True, hora_ini_conflitante, hora_fim_conflitante) se o novo intervalo
    sobrepuser algum lançamento já existente naquele dia/turno/máquina - não importa
    se o outro lançamento é 'Produzindo' ou 'Máquina Parada'."""
    registros = obter_registros_do_dia(maquina, turno)

    novo_ini_min = novo_ini.hour * 60 + novo_ini.minute
    novo_fim_min = novo_fim.hour * 60 + novo_fim.minute
    if novo_fim_min <= novo_ini_min:
        novo_fim_min += 24 * 60

    for h_ini_str, h_fim_str in registros:
        ini_min = int(h_ini_str[:2]) * 60 + int(h_ini_str[3:5])
        fim_min = int(h_fim_str[:2]) * 60 + int(h_fim_str[3:5])
        if fim_min <= ini_min:
            fim_min += 24 * 60

        if novo_ini_min < fim_min and ini_min < novo_fim_min:
            return True, h_ini_str, h_fim_str

    return False, None, None

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

col_top1, col_top2, col_top3 = st.columns([1, 1, 1])
with col_top1:
    maquina_selecionada = st.selectbox("Máquina:", LISTA_MAQUINAS)
with col_top2:
    turno_selecionado = st.selectbox("Turno:", ["A (05:30 às 13:50)", "B (13:50 às 22:10)", "C (22:10 às 05:30)"])[0]
with col_top3:
    data_referencia = st.date_input("📅 Data de referência (consulta):", value=date.today(), format="DD/MM/YYYY")

if maquina_selecionada != "--- Selecione uma Máquina ---":

    st.markdown(
        f"<h1 style='text-align: center;'>{maquina_selecionada} - Turno {turno_selecionado}</h1>",
        unsafe_allow_html=True
    )

    eh_hoje = (data_referencia == date.today())

    # Busca o último horário para preenchimento automático contínuo (sempre baseado em hoje)
    ultimo_fim = obter_ultimo_registro_maquina_turno(maquina_selecionada, turno_selecionado)
    if ultimo_fim:
        hora_inicio_calc = datetime.strptime(ultimo_fim, "%H:%M").time()
    else:
        hora_inicio_calc = time(5, 30) if turno_selecionado == "A" else time(13, 50) if turno_selecionado == "B" else time(22, 10)

    dt_fim_sugerido = (datetime.combine(datetime.today(), hora_inicio_calc) + timedelta(minutes=15)).time()

    # --- ÁREA DE PREENCHIMENTO (TOPO) - só faz sentido lançar para o dia de hoje ---
    if eh_hoje:
        with st.expander("📝 NOVO APONTAMENTO (Clique para expandir/recolher)", expanded=True):
            if st.session_state["msg_sucesso"]:
                st.success(st.session_state["msg_sucesso"])
                st.session_state["msg_sucesso"] = ""
            if st.session_state["msg_erro"]:
                st.error(st.session_state["msg_erro"])
                st.session_state["msg_erro"] = ""

            with st.form("form_apontamento", clear_on_submit=False):
                c1, c2, c3, c4 = st.columns([1.5, 2, 2, 1])
                with c1:
                    op_input = st.text_input("OP:", value=st.session_state["persist_op"])
                with c2:
                    operador_input = st.text_input("Operador:", value=st.session_state["persist_operador"])
                with c3:
                    produto_input = st.text_input("Produto:", value=st.session_state["persist_sku"])
                with c4:
                    status_atividade = st.selectbox("Status:", ["Produzindo", "Máquina Parada"], key="in_status")

                t1, t2, t3, t4 = st.columns(4)
                with t1:
                    hi_h = st.number_input("Início - Hora", min_value=0, max_value=23, step=1,
                                            value=hora_inicio_calc.hour, key="in_hi_h")
                with t2:
                    hi_m = st.number_input("Início - Min", min_value=0, max_value=59, step=1,
                                            value=hora_inicio_calc.minute, key="in_hi_m")
                with t3:
                    hf_h = st.number_input("Fim - Hora", min_value=0, max_value=23, step=1,
                                            value=dt_fim_sugerido.hour, key="in_hf_h")
                with t4:
                    hf_m = st.number_input("Fim - Min", min_value=0, max_value=59, step=1,
                                            value=dt_fim_sugerido.minute, key="in_hf_m")

                hora_inicio = time(int(hi_h), int(hi_m))
                hora_fim = time(int(hf_h), int(hf_m))

                if status_atividade == "Produzindo":
                    p1, p2, p3, p4 = st.columns(4)
                    with p1:
                        qtd_boa_kg = st.number_input("Prod. Boa (kg):", min_value=0.0, step=1.0, key="in_boa_kg")
                    with p2:
                        qtd_boa_m = st.number_input("Prod. Boa (m):", min_value=0.0, step=1.0, key="in_boa_m")
                    with p3:
                        qtd_perda_kg = st.number_input("Perda (kg):", min_value=0.0, step=1.0, key="in_perda_kg")
                    with p4:
                        velocidade_padrao = st.number_input("Vel. Padrão (m/min):", min_value=0.0, step=1.0, key="in_vel")

                    c_just1, c_just2 = st.columns(2)
                    with c_just1:
                        tipo_perda = st.selectbox("Tipo de Perda:", ["Nenhuma", "Trim", "Borra", "Sucata", "Material B", "Refilo"], key="in_tipo_perda")
                    with c_just2:
                        cod_perda = st.selectbox("Cód. Perda:", ["Nenhum"] + CODIGOS_PROCESSO, key="in_cod_perda")
                    just_parada = "Nenhum (Produzindo)"
                else:
                    qtd_boa_kg = 0.0
                    qtd_boa_m = 0.0
                    qtd_perda_kg = 0.0
                    velocidade_padrao = 0.0
                    tipo_perda = "Nenhuma"
                    cod_perda = "Nenhum"
                    just_parada = st.selectbox("🛑 Cód. Parada (motivo obrigatório):", CODIGOS_PROCESSO, key="in_just_parada")

                observacoes = st.text_input("Observações (Opcional):", key="in_obs")

                submit = st.form_submit_button("💾 Lançar na Planilha", type="primary", use_container_width=True)
                if submit:
                    conflito, c_ini, c_fim = verificar_conflito(maquina_selecionada, turno_selecionado, hora_inicio, hora_fim)
                    if conflito:
                        st.session_state["msg_erro"] = (
                            f"⚠️ Conflito de horário! Já existe um lançamento das {c_ini} às {c_fim} "
                            f"para {maquina_selecionada} no Turno {turno_selecionado}. Ajuste o horário e tente novamente."
                        )
                        st.rerun()
                    else:
                        st.session_state["persist_op"] = op_input
                        st.session_state["persist_operador"] = operador_input
                        st.session_state["persist_sku"] = produto_input

                        inserir_apontamento(
                            maquina_selecionada, turno_selecionado, op_input, operador_input, produto_input, status_atividade,
                            hora_inicio.strftime("%H:%M"), hora_fim.strftime("%H:%M"), qtd_boa_kg, qtd_boa_m, qtd_perda_kg,
                            tipo_perda, cod_perda, just_parada, observacoes, velocidade_padrao
                        )
                        st.session_state["msg_sucesso"] = f"✅ Lançamento {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')} salvo!"

                        # Limpa tudo, exceto Máquina/Turno (fora do form) e OP/Operador/Produto (persistidos acima)
                        for k in ["in_status", "in_hi_h", "in_hi_m", "in_hf_h", "in_hf_m", "in_boa_kg", "in_boa_m",
                                  "in_perda_kg", "in_vel", "in_tipo_perda", "in_cod_perda", "in_just_parada", "in_obs"]:
                            st.session_state.pop(k, None)
                        st.rerun()
    else:
        st.info("📅 Você está consultando uma data diferente de hoje. O formulário de lançamento fica disponível apenas para o dia atual.")

    # --- ESPELHO DA PLANILHA ---
    st.markdown(f"### 📋 Controle de Processo - {data_referencia.strftime('%d/%m/%Y')} - Turno {turno_selecionado}")
    df_turno = ler_dados(maquina_selecionada, turno_selecionado, data_filtro=data_referencia)

    if not df_turno.empty:
        df_display = df_turno.copy()
        df_display = df_display[[
            "hora_inicio", "hora_fim", "ordem_producao", "produto", "status_atividade",
            "qtd_boa_kg", "qtd_boa_m", "qtd_perda_kg", "velocidade_padrao", "justificativa_parada", "observacoes"
        ]]
        df_display.columns = [
            "Início", "Fim", "OP", "Produto", "Status", "Prod. Bom (Kg)", "Prod. Bom (m)",
            "Perda (Kg)", "Vel. Padrão (m/min)", "Motivo Improdutivo", "Observações"
        ]
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
        prod_bom_kg = df_turno["qtd_boa_kg"].sum()
        prod_bom_m = df_turno["qtd_boa_m"].sum()

        tempo_total = tempo_processo + tempo_improdutivo
        oee_disponibilidade = (tempo_processo / tempo_total * 100) if tempo_total > 0 else 0.0

        # Volume esperado = soma de (velocidade padrão x minutos) de cada lançamento "Produzindo"
        df_prod = df_turno[df_turno["status_atividade"] == "Produzindo"]
        volume_esperado_m = (df_prod["velocidade_padrao"] * df_prod["minutos"]).sum()
        velocidade_media_real = (prod_bom_m / tempo_processo) if tempo_processo > 0 else 0.0
        oee_performance = (prod_bom_m / volume_esperado_m * 100) if volume_esperado_m > 0 else 0.0

        st.markdown("---")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("⏱️ Tempo Total PROCESSO", f"{int(tempo_processo)} min")
        k2.metric("🛑 Tempo Total PARADA", f"{int(tempo_improdutivo)} min")
        k3.metric("📦 Prod. Aprovada (Kg)", f"{prod_bom_kg:,.1f}")
        k4.metric("📊 OEE (Disponibilidade)", f"{oee_disponibilidade:.1f} %")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("🚀 Volume Esperado (m)", f"{volume_esperado_m:,.1f}")
        k6.metric("📏 Prod. Real (m)", f"{prod_bom_m:,.1f}")
        k7.metric("⚡ Velocidade Média Real (m/min)", f"{velocidade_media_real:,.1f}")
        k8.metric("🎯 OEE Performance (Real/Esperado)", f"{oee_performance:.1f} %")

        # --- GRÁFICO ESPERADO x REAL ---
        st.markdown("<br>", unsafe_allow_html=True)
        df_comp = pd.DataFrame({
            "Categoria": ["Esperado", "Real"],
            "Metros": [volume_esperado_m, prod_bom_m]
        })
        fig_comp = px.bar(
            df_comp, x="Categoria", y="Metros", color="Categoria", text="Metros",
            color_discrete_map={"Esperado": "#95A5A6", "Real": "#2ECC71"},
            title="Volume Esperado x Real (m)", height=280
        )
        fig_comp.update_traces(texttemplate="%{text:,.1f} m", textposition="outside")
        fig_comp.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_comp, use_container_width=True)

        # --- LINHA DO TEMPO VISUAL ---
        st.markdown("<br>", unsafe_allow_html=True)
        base_str = data_referencia.strftime("%Y-%m-%d")
        df_turno["Inicio_DT"] = pd.to_datetime(base_str + " " + df_turno["hora_inicio"])
        df_turno["Fim_DT"] = pd.to_datetime(base_str + " " + df_turno["hora_fim"])
        # Corrige quando o horário "vira" a meia-noite (fim menor que início)
        df_turno.loc[df_turno["Fim_DT"] < df_turno["Inicio_DT"], "Fim_DT"] += pd.Timedelta(days=1)

        df_turno["obs_hover"] = df_turno["observacoes"].fillna("").replace("", "Sem observações")
        df_turno["motivo_hover"] = df_turno.apply(
            lambda r: r["justificativa_parada"] if r["status_atividade"] == "Máquina Parada"
            else (f"Perda: {r['tipo_perda']}" if r["tipo_perda"] not in (None, "Nenhuma") else "Produção normal"),
            axis=1
        )

        fig = px.timeline(
            df_turno, x_start="Inicio_DT", x_end="Fim_DT", y="status_atividade", color="status_atividade",
            color_discrete_map={"Produzindo": "#2ECC71", "Máquina Parada": "#E74C3C"},
            custom_data=["ordem_producao", "produto", "hora_inicio", "hora_fim", "motivo_hover", "obs_hover"],
            height=280, title="Mapeamento Gráfico do Turno"
        )
        fig.update_traces(
            hovertemplate=(
                "<b>OP %{customdata[0]}</b> — %{customdata[1]}<br>"
                "⏱ %{customdata[2]} às %{customdata[3]}<br>"
                "📋 %{customdata[4]}<br>"
                "📝 %{customdata[5]}"
                "<extra></extra>"
            )
        )
        fig.update_layout(
            xaxis=dict(tickformat="%H:%M", title=None),
            yaxis=dict(title=None),
            showlegend=False,
            margin=dict(t=40, b=0, l=0, r=0),
            hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial", bordercolor="#CCCCCC")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"Nenhum lançamento encontrado para {maquina_selecionada} - Turno {turno_selecionado} em {data_referencia.strftime('%d/%m/%Y')}.")

import pandas as pd
import streamlit as st
import requests
import base64
import plotly.express as px
from config import *

# =====================================================
# 🎨 FUNDO PERSONALIZADO
# =====================================================
def add_bg_from_local(image_file):
    with open(image_file, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/png;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}

    /* remove fundo branco dos blocos */
    .block-container {{
        background-color: rgba(0,0,0,40);
    }}

    /* sidebar leve transparente */
    section[data-testid="stSidebar"] {{
        background-color: rgba(0,0,0,0.25);
    }}

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

add_bg_from_local("fundo.png")

st.set_page_config(layout="wide")
st.title("𖠿 Descomplica")

st.sidebar.title("☰ MENU")

menu = st.sidebar.radio(
    "Navegação",
    [
        "🐊 Lacoste",
        "🐊 Estoque 900118",
        "🍲 Le Creuset",
        "𝒜𝔭𝔭𝔯𝑜𝔳𝔢",
    ]
)

# =====================================================
# 🔌 METABASE CACHE
# =====================================================

@st.cache_data(ttl=300)
def puxar_pergunta(pergunta_id):
    url = f"{METABASE_URL}/api/card/{pergunta_id}/query/json"
    headers = {"X-Metabase-Session": SESSION_TOKEN}
    response = requests.post(url, headers=headers)

    if response.status_code != 200:
        st.error(f"❌ Erro ao consultar pergunta {pergunta_id}")
        st.stop()

    return pd.DataFrame(response.json())

# =====================================================
# 🧠 CLASSIFICAÇÃO
# =====================================================

def classificar(row):
    m0 = row.get("M0", 0)
    mr = row.get("MR", 0)
    pp = row.get("PP", 0)
    re = row.get("RE", 0)
    pedido = row["pedido"]

    picking = m0 + mr
    com_pp = picking + pp
    com_re = com_pp + re

    if pedido == 0:
        return "Sem Pedido"
    if picking >= pedido:
        return "🟢 Picking"
    elif com_pp >= pedido:
        return "🟠 Derrubada"
    elif com_re >= pedido:
        return "🔵 Armazenagem"
    else:
        return "🔴 Possível Ruptura"

# =====================================================
# 🚀 MOTOR PRINCIPAL
# =====================================================

def processar_operacao(pergunta_estoque, pergunta_pedidos):

    if st.button("🔄 Atualizar dados"):
        st.session_state[f"dados_{menu}"] = True

    if f"dados_{menu}" not in st.session_state:
        st.info("Clique em atualizar dados")
        st.stop()

    with st.spinner("Puxando dados do Metabase..."):
        estoque = puxar_pergunta(pergunta_estoque)
        pedidos = puxar_pergunta(pergunta_pedidos)

    st.success("Dados carregados!")

    # ================= LIMPEZA
    estoque["QTD Disponível"] = pd.to_numeric(estoque["QTD Disponível"], errors="coerce").fillna(0)
    pedidos["Soma de Qtd Atual"] = pd.to_numeric(pedidos["Soma de Qtd Atual"], errors="coerce").fillna(0)

    estoque["ref"] = estoque["Produto"].astype(str)
    pedidos["ref"] = pedidos["Referencia"].astype(str)

    # ================= ESTOQUE POR AREA
    est = estoque.groupby(["ref", "Área"])["QTD Disponível"].sum().reset_index()

    pivot = est.pivot_table(
        index="ref",
        columns="Área",
        values="QTD Disponível",
        fill_value=0
    ).reset_index()

    for col in ["M0", "MR", "PP", "RE"]:
        if col not in pivot.columns:
            pivot[col] = 0

    # ================= PEDIDOS
    ped = pedidos.groupby("ref")["Soma de Qtd Atual"].sum().reset_index()
    ped.columns = ["ref", "pedido"]

    final = pivot.merge(ped, on="ref", how="left").fillna(0)

    # ================= CLASSIFICAR
    final["Status"] = final.apply(classificar, axis=1)
    final["Saldo_pos"] = (final["M0"] + final["MR"] + final["PP"]) - final["pedido"]

    # =====================================================
    # 🚨 TORRE DE CONTROLE
    # =====================================================

    st.markdown("---")
    st.markdown("## 📊 Visão Macro por SKU")

    k1, k2, k3, k4 = st.columns(4)

    k1.metric("🟢 Picking OK", int((final["Status"] == "🟢 Picking").sum()))
    k2.metric("🟠 Derrubada", int((final["Status"] == "🟠 Derrubada").sum()))
    k3.metric("🔵 Armazenagem", int((final["Status"] == "🔵 Armazenagem").sum()))
    k4.metric("🔴 Ruptura", int((final["Status"] == "🔴 Possível Ruptura").sum()))

    status_count = final["Status"].value_counts().reset_index()
    status_count.columns = ["Status", "Qtd"]

    fig = px.pie(status_count, names="Status", values="Qtd", title="Distribuição logística")
    st.plotly_chart(fig, width="stretch")

    # ================= MACRO
    st.markdown("---")
    st.markdown("## 📊 Visão Macro por Peças")

    macro = final.groupby("Status")["pedido"].sum().reset_index()
    macro.columns = ["Categoria", "Peças em pedidos"]
    macro = macro.sort_values(by="Peças em pedidos", ascending=False)

    fig_macro = px.bar(
        macro,
        x="Categoria",
        y="Peças em pedidos",
        text_auto=True,
        title="Volume de peças por categoria operacional"
    )
    st.plotly_chart(fig_macro, width="stretch")

    fig_pizza = px.pie(
        macro,
        names="Categoria",
        values="Peças em pedidos",
        title="Distribuição de carga operacional"
    )
    st.plotly_chart(fig_pizza, width="stretch")

    # ================= CRÍTICOS
    st.markdown("---")
    st.markdown("## 🚨 SKUs Críticos da Operação")

    criticos = final[
        (final["Status"] == "🟠 Derrubada") |
        (final["Status"] == "🔵 Armazenagem") |
        (final["Status"] == "🔴 Possível Ruptura")
    ]

    if len(criticos) > 0:
        st.dataframe(criticos.sort_values("pedido", ascending=False), width="stretch")
    else:
        st.success("Nenhum SKU crítico 🎯")

    # =====================================================
    # 🧠 DERRUBADA INTELIGENTE
    # =====================================================
    st.markdown("---")
    st.markdown("## 🧠 Derrubada Compactada")

    derrubada_df = final[final["Status"] == "🟠 Derrubada"]

    if len(derrubada_df) == 0:
        st.success("Nenhuma derrubada necessária")

    else:
        detalhes = estoque.copy()
        detalhes["ref"] = detalhes["Produto"]

    onda_final = []

    for _, row in derrubada_df.iterrows():
        ref = row["ref"]
        pedido = row["pedido"]

        posicoes = detalhes[
            (detalhes["ref"] == ref) &
            (detalhes["Área"] == "PP")
        ].copy()

        if len(posicoes) == 0:
            continue

        posicoes = posicoes.sort_values(by="QTD Disponível", ascending=False)

        soma = 0

        for _, p in posicoes.iterrows():
            qtd = p["QTD Disponível"]
            soma += qtd

            onda_final.append({
                "Ref": ref,
                "Endereço": p["Endereço"],
                "UZ/Pallet": p["UZ/Pallet"],
                "Área": p["Área"],
                "Qtd endereço": qtd,
                "Pedido": pedido,
                "Acumulado": soma
            })

            if soma >= pedido:
                break

    onda_df = pd.DataFrame(onda_final)

    st.warning(f"⚠️ {len(onda_df)} endereços necessários para atender pedidos")
    st.dataframe(onda_df, width="stretch")

    import io
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        onda_df.to_excel(writer, index=False, sheet_name="Derrubada")

    st.download_button(
        label="📥 BAIXAR DERRUBADA OTIMIZADA CD",
        data=output.getvalue(),
        file_name="derrubada_otimizada_cd.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # =====================================================
    # 🚨 PEDIDOS SEM POSIÇÃO NO ESTOQUE
    # =====================================================
    st.markdown("---")
    st.markdown("## 🚨 Referências sem posição em estoque")

    # refs existentes no estoque
    refs_estoque = set(pivot["ref"].astype(str))

    pedidos_base = pedidos.copy()
    pedidos_base["ref"] = pedidos_base["Referencia"].astype(str)
    pedidos_base["qtd"] = pd.to_numeric(
        pedidos_base["Soma de Qtd Atual"], errors="coerce"
    ).fillna(0)

    # pegar numero pedido = 2ª coluna metabase
    colunas_ped = list(pedidos_base.columns)
    col_num_pedido = colunas_ped[1] if len(colunas_ped) >= 2 else None

    # filtrar sem estoque
    sem_estoque = pedidos_base[
        ~pedidos_base["ref"].isin(refs_estoque)
    ].copy()

    if len(sem_estoque) == 0:
        st.success("Nenhuma referência sem posição de estoque 🎯")
    else:

        if col_num_pedido:
            rel_sem = sem_estoque[[col_num_pedido, "ref", "qtd"]].copy()
            rel_sem.columns = ["Pedido", "Referência", "Qtd Solicitada"]
        else:
            rel_sem = sem_estoque[["ref", "qtd"]].copy()
            rel_sem.columns = ["Referência", "Qtd Solicitada"]
            rel_sem.insert(0, "Pedido", "-")

        rel_sem = rel_sem.sort_values("Qtd Solicitada", ascending=False)

        st.error(f"🚨 {len(rel_sem)} referências sem posição no estoque")
        st.dataframe(rel_sem, width="stretch", height=400)

        # excel
        import io
        output_zero = io.BytesIO()

        with pd.ExcelWriter(output_zero, engine="openpyxl") as writer:
            rel_sem.to_excel(writer, index=False, sheet_name="Sem estoque")

        st.download_button(
            label="📥 BAIXAR CORTES",
            data=output_zero.getvalue(),
            file_name="pedidos_sem_estoque.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # =====================================================
    # 🚨 RELATÓRIO COMPLETO DE RUPTURA
    # =====================================================
    st.markdown("---")
    st.markdown("## 🚨 Visão Analítica de Ruptura")

    # filtrar apenas rupturas
    ruptura_view = final[final["Status"] == "🔴 Possível Ruptura"].copy()

    if len(ruptura_view) == 0:
        st.success("Nenhuma ruptura encontrada 🎯")
        return

    # =====================================================
    # 🔢 CAPTURAR NUMERO DO PEDIDO (2ª COLUNA METABASE)
    # =====================================================
    colunas_ped = list(pedidos.columns)

    if len(colunas_ped) >= 2:
        col_num_pedido = colunas_ped[1]  # segunda coluna = numero pedido

        ped_num = pedidos.copy()
        ped_num["ref"] = ped_num["Referencia"].astype(str)

        ped_num = ped_num[["ref", col_num_pedido]].drop_duplicates()
        ped_num.columns = ["ref", "Numero Pedido"]

        ruptura_view = ruptura_view.merge(ped_num, on="ref", how="left")
    else:
        ruptura_view["Numero Pedido"] = "-"

    # =====================================================
    # GARANTIR COLUNAS DE ESTOQUE
    # =====================================================
    for col in ["M0", "MR", "PP", "RE"]:
        if col not in ruptura_view.columns:
            ruptura_view[col] = 0

    # =====================================================
    # ORGANIZAÇÃO FINAL
    # =====================================================
    ruptura_view = ruptura_view[[
        "Numero Pedido",
        "ref",
        "pedido",
        "M0",
        "MR",
        "PP",
        "RE"
    ]]

    ruptura_view.columns = [
        "Pedido",
        "Referência",
        "Qtd Pedido",
        "Qtd M0",
        "Qtd MR",
        "Qtd PP",
        "Qtd RE"
    ]

    # ordenar por maior impacto
    ruptura_view = ruptura_view.sort_values("Qtd Pedido", ascending=False)

    # =====================================================
    # EXIBIÇÃO
    # =====================================================
    st.error(f"🚨 {len(ruptura_view)} SKUs em ruptura operacional")

    st.dataframe(
        ruptura_view,
        width="stretch",
        height=500
    )

    # =====================================================
    # EXPORTAÇÃO EXCEL
    # =====================================================
    import io
    output_rup = io.BytesIO()

    with pd.ExcelWriter(output_rup, engine="openpyxl") as writer:
        ruptura_view.to_excel(writer, index=False, sheet_name="Ruptura")

    st.download_button(
        label="📥 BAIXAR RELATÓRIO DE RUPTURA",
        data=output_rup.getvalue(),
        file_name="relatorio_ruptura_cd.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =====================================================
# CHAMADAS POR MENU
# =====================================================

if menu == "🐊 Lacoste":
    processar_operacao(PERGUNTA_ESTOQUE_LA, PERGUNTA_PEDIDOS_LA)

if menu == "🐊 Estoque 900118":
    processar_operacao(PERGUNTA_ESTOQUE_18, PERGUNTA_PEDIDOS_18)

if menu == "🍲 Le Creuset":
    processar_operacao(PERGUNTA_ESTOQUE_LC, PERGUNTA_PEDIDOS_LC)

if menu == "𝒜𝔭𝔭𝔯𝑜𝔳𝔢":
    processar_operacao(PERGUNTA_ESTOQUE_APRV, PERGUNTA_PEDIDOS_APRV)






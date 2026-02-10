import pandas as pd
import streamlit as st
import requests
import plotly.express as px
from config import *

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

# =========================================
# FUNÇÃO CONSULTA METABASE
# =========================================
def puxar_pergunta(pergunta_id):

    url = f"{METABASE_URL}/api/card/{pergunta_id}/query/json"

    headers = {
        "X-Metabase-Session": SESSION_TOKEN
    }

    response = requests.post(url, headers=headers)

    if response.status_code != 200:
        st.error(f"❌ Erro ao consultar pergunta {pergunta_id}")
        st.stop()

    data = response.json()
    return pd.DataFrame(data)

# =========================================
# BOTÃO
# =========================================
if st.button("🔄 Atualizar dados"):
    st.session_state["dados"] = True

if "dados" not in st.session_state:
    st.info("Clique em atualizar dados")
    st.stop()

# =========================================
# PUXAR DADOS
# =========================================
with st.spinner("Puxando dados do Metabase..."):
    estoque = puxar_pergunta(PERGUNTA_ESTOQUE)
    pedidos = puxar_pergunta(PERGUNTA_PEDIDOS)

st.success("Dados carregados!")

# =========================================
# LIMPEZA
# =========================================

estoque["QTD Disponível"] = pd.to_numeric(estoque["QTD Disponível"], errors="coerce").fillna(0)
pedidos["Soma de Qtd Atual"] = pd.to_numeric(pedidos["Soma de Qtd Atual"], errors="coerce").fillna(0)

estoque["UZ/Pallet"] = estoque["UZ/Pallet"]
estoque["ref"] = estoque["Produto"].astype(str)
pedidos["ref"] = pedidos["Referencia"].astype(str)

# =========================================
# ESTOQUE POR AREA
# =========================================

est = estoque.groupby(["ref","Área"])["QTD Disponível"].sum().reset_index()

pivot = est.pivot_table(
    index="ref",
    columns="Área",
    values="QTD Disponível",
    fill_value=0
).reset_index()

for col in ["M0","MR","PP"]:
    if col not in pivot.columns:
        pivot[col] = 0

# =========================================
# PEDIDOS
# =========================================

ped = pedidos.groupby("ref")["Soma de Qtd Atual"].sum().reset_index()
ped.columns = ["ref","pedido"]

# =========================================
# JOIN
# =========================================

final = pivot.merge(ped, on="ref", how="left").fillna(0)

# =========================================
# CLASSIFICAÇÃO LOGÍSTICA
# =========================================

def classificar(row):

    m0 = row.get("M0",0)
    mr = row.get("MR",0)
    pp = row.get("PP",0)
    re = row.get("RE",0)
    pedido = row["pedido"]

    picking = m0 + mr
    com_pp = picking + pp
    com_re = com_pp + re

    if pedido == 0:
        return "Sem Pedido"

    # atende só com picking
    if picking >= pedido:
        return "🟢 Picking"

    # precisa derrubar PP
    elif com_pp >= pedido:
        return "🟠 Derrubada"

    # precisa armazenagem RE
    elif com_re >= pedido:
        return "🔵 Armazenagem"

    # nem assim atende
    else:
        return "🔴 Possível Ruptura"

final["Status"] = final.apply(classificar, axis=1)
final["Saldo_pos"] = (final["M0"] + final["MR"] + final["PP"]) - final["pedido"]

# =========================================
# 🚨 TORRE DE CONTROLE LOGÍSTICA
# =========================================

if menu == "🐊 Lacoste":

    st.markdown("## 🚨 Torre de Controle Operacional")

    ruptura = final[final["Status"]=="🔴 Possível Ruptura"]
    derrubada = final[final["Status"]=="🟠 Derrubada"]
    armazenagem = final[final["Status"]=="🔵 Armazenagem"]

    if len(ruptura) > 0:
        st.error(f"🚨 RUPTURA: {len(ruptura)} SKUs não atendem pedido")

    if len(derrubada) > 0:
        st.warning(f"⚠️ DERRUBADA NECESSÁRIA: {len(derrubada)} SKUs")

    if len(armazenagem) > 0:
        st.info(f"🏬 ARMAZENAGEM: {len(armazenagem)} SKUs precisam RE")

    if len(ruptura)==0 and len(derrubada)==0 and len(armazenagem)==0:
        st.success("🟢 OPERAÇÃO ESTÁVEL — sem riscos logísticos")

    st.markdown("---")
    st.markdown("## 🎯 Painel Executivo Operacional")

    k1,k2,k3,k4 = st.columns(4)

    k1.metric(
        "🟢 Picking OK",
        int((final["Status"]=="🟢 Picking").sum())
    )

    k2.metric(
        "🟠 Derrubada",
        int((final["Status"]=="🟠 Derrubada").sum())
    )

    k3.metric(
        "🔵 Armazenagem",
        int((final["Status"]=="🔵 Armazenagem").sum())
    )

    k4.metric(
        "🔴 Ruptura",
        int((final["Status"]=="🔴 Possível Ruptura").sum())
    )

    status_count = final["Status"].value_counts().reset_index()
    status_count.columns = ["Status","Qtd"]

    fig = px.pie(status_count, names="Status", values="Qtd", title="Distribuição logística")
    st.plotly_chart(fig, width="stretch")

# =========================================
# 📊 VISÃO MACRO PEÇAS POR CATEGORIA
# =========================================

    st.markdown("---")
    st.markdown("## 📊 Visão Macro de Peças por Categoria")

    # soma peças por status
    macro = final.groupby("Status")["pedido"].sum().reset_index()
    macro.columns = ["Categoria","Peças em pedidos"]

    # ordenar maior volume
    macro = macro.sort_values(by="Peças em pedidos", ascending=False)

    # KPIs executivos
    c1, c2, c3, c4 = st.columns(4)

    def get_val(cat):
        val = macro.loc[macro["Categoria"]==cat, "Peças em pedidos"]
        return int(val.values[0]) if len(val)>0 else 0

    # gráfico barras
    import plotly.express as px

    fig_macro = px.bar(
        macro,
        x="Categoria",
        y="Peças em pedidos",
        text_auto=True,
        title="Volume de peças por categoria operacional"
    )

    st.plotly_chart(fig_macro, width="stretch")

    # gráfico pizza executivo
    fig_pizza = px.pie(
        macro,
        names="Categoria",
        values="Peças em pedidos",
        title="Distribuição de carga operacional"
    )

    st.plotly_chart(fig_pizza, width="stretch")

    st.markdown("---")
    st.markdown("## 🚨 SKUs Críticos da Operação")

    criticos = final[
        (final["Status"]=="🟠 Derrubada") |
        (final["Status"]=="🔵 Armazenagem") |
        (final["Status"]=="🔴 Possível Ruptura")
    ]

    if len(criticos) > 0:
        st.dataframe(criticos.sort_values("pedido", ascending=False), width="stretch")
    else:
        st.success("Nenhum SKU crítico 🎯")


# =========================================
# 🧠 DERRUBADA INTELIGENTE PROFISSIONAL
# =========================================

    st.markdown("---")
    st.markdown("## 🧠 Derrubada Inteligente (maior saldo / menos endereços)")

    derrubada_df = final[final["Status"]=="🟠 Derrubada"]

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
                (detalhes["ref"]==ref) &
                (detalhes["Área"]=="PP")
            ].copy()

            if len(posicoes) == 0:
                continue

            # 🔵 MAIOR SALDO PRIMEIRO (menos endereços)
            posicoes = posicoes.sort_values(
                by="QTD Disponível",
                ascending=False
            )

            soma = 0
            usados = 0

            for _, p in posicoes.iterrows():

                qtd = p["QTD Disponível"]
                soma += qtd
                usados += 1

                onda_final.append({
                    "Ref": ref,
                    "Endereço": p["Endereço"],
                    "UZ/Pallet": p["UZ/Pallet"],
                    "Área": p["Área"],
                    "Qtd endereço": qtd,
                    "Pedido": pedido,
                    "Acumulado": soma
                })

                # 🔴 parou ao atingir pedido
                if soma >= pedido:
                    break

        onda_df = pd.DataFrame(onda_final)

        st.warning(f"⚠️ {len(onda_df)} endereços necessários para atender pedidos")
        st.dataframe(onda_df, width="stretch")

    # =====================================
    # EXCEL OPERACIONAL
    # =====================================

        import io
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            onda_df.to_excel(writer, index=False, sheet_name="Derrubada")

        excel_data = output.getvalue()

        st.download_button(
            label="📥 BAIXAR DERRUBADA OTIMIZADA CD",
            data=excel_data,
            file_name="derrubada_otimizada_cd.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

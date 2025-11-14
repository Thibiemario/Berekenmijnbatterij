import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px

# === Pagina ===
st.set_page_config(page_title="🔋 Batterij Simulatie", layout="wide")
st.title("🔋 Simulatie van batterij- en netverbruik (met reactietijd)")

st.markdown("""
Deze app simuleert het gedrag van een thuisbatterij op basis van kwartierwaarden.
Upload een CSV met kolommen **datum, tijdstip, type, vermogen** en bekijk:
- Hoeveel energie je **van/naar het net** haalt  
- Hoe de **batterijcapaciteit** en **reactietijd** dit beïnvloeden  
- De **financiële besparing per maand**  
- Hoelang de batterij **vol of leeg** is  
""")

# === Sidebar: instellingen ===
st.sidebar.header("⚙️ Simulatie-instellingen")

batterij_capaciteit = st.sidebar.number_input("Batterijcapaciteit (kWh)", min_value=1.0, max_value=100.0, value=5.0, step=0.1)
max_vermogen_kW = st.sidebar.number_input("Maximaal vermogen omvormer (kW)", min_value=0.1, max_value=20.0, value=2.5, step=0.1)
eff_laden = st.sidebar.slider("Efficiëntie opladen (%)", 70, 100, 95) / 100
eff_ontladen = st.sidebar.slider("Efficiëntie ontladen (%)", 70, 100, 95) / 100
soc_min_pct = st.sidebar.slider("Minimum SoC (%)", 0, 50, 10)
soc_max_pct = st.sidebar.slider("Maximum SoC (%)", 50, 100, 90)
reactietijd_laden = st.sidebar.slider("Reactietijd opladen (s)", 0, 60, 10)
reactietijd_ontladen = st.sidebar.slider("Reactietijd ontladen (s)", 0, 60, 10)
prijs_import = st.sidebar.number_input("Prijs import (€/kWh)", value=0.30, step=0.01)
prijs_export = st.sidebar.number_input("Prijs export (€/kWh)", value=0.07, step=0.01)

uploaded_file = st.sidebar.file_uploader("📤 Upload CSV-bestand met kwartierwaarden", type=["csv"])

# === Simulatie uitvoeren ===
if uploaded_file:
    df = pd.read_csv(uploaded_file, sep=';', decimal=',')
    df.columns = df.columns.str.lower().str.strip()
    vereist = {"datum", "tijdstip", "type", "vermogen"}

    if not vereist.issubset(df.columns):
        st.error(f"⚠️ CSV moet de kolommen bevatten: {vereist}")
    else:
        # Data voorbereiden
        df["vermogen"] = df["vermogen"].astype(str).str.replace(" ", "").str.replace(",", ".")
        df["vermogen"] = pd.to_numeric(df["vermogen"], errors="coerce")
        df["datetime"] = pd.to_datetime(df["datum"] + " " + df["tijdstip"], dayfirst=True, errors="coerce")
        df["type"] = df["type"].str.lower().str.strip()
        df["afname"] = df["type"].str.contains("afname", case=False) * df["vermogen"]
        df["injectie"] = df["type"].str.contains("injectie", case=False) * df["vermogen"]
        df_kwartier = df.groupby("datetime", as_index=False)[["afname", "injectie"]].sum().sort_values("datetime")

        # Simulatie-instellingen
        batterij_niveau = batterij_capaciteit / 2
        kwartier_uur = 0.25
        max_energie_per_kwartier = max_vermogen_kW * kwartier_uur
        soc_min = soc_min_pct / 100 * batterij_capaciteit
        soc_max = soc_max_pct / 100 * batterij_capaciteit
        vertraging_laden = max(0, min(1, 1 - reactietijd_laden / 900))
        vertraging_ontladen = max(0, min(1, 1 - reactietijd_ontladen / 900))

        # Simulatie doorlopen
        resultaten = []
        energie_op_batterij = energie_van_net = energie_naar_net = 0.0
        energie_zonder_batterij_van_net = energie_zonder_batterij_naar_net = 0.0

        for _, r in df_kwartier.iterrows():
            afname = r["afname"]
            injectie = r["injectie"]
            energie_zonder_batterij_van_net += afname
            energie_zonder_batterij_naar_net += injectie

            # Laden
            potentieel_opladen = injectie * eff_laden * vertraging_laden
            effectief_opladen = min(potentieel_opladen, max_energie_per_kwartier, soc_max - batterij_niveau)
            batterij_niveau += effectief_opladen
            energie_op_batterij += effectief_opladen
            naar_net = max(injectie - (effectief_opladen / (eff_laden * vertraging_laden + 1e-9)), 0)

            # Ontladen
            potentieel_ontladen = min(afname / (eff_ontladen * vertraging_ontladen + 1e-9),
                                      max_energie_per_kwartier,
                                      batterij_niveau - soc_min)
            effectief_ontladen = potentieel_ontladen * eff_ontladen * vertraging_ontladen
            batterij_niveau -= potentieel_ontladen
            van_net = max(afname - effectief_ontladen, 0)
            energie_van_net += van_net
            energie_naar_net += naar_net

            resultaten.append({
                "tijd": r["datetime"],
                "afname (kWh)": afname,
                "injectie (kWh)": injectie,
                "opladen (kWh)": effectief_opladen,
                "ontladen (kWh)": effectief_ontladen,
                "van_net (kWh)": van_net,
                "naar_net (kWh)": naar_net,
                "batterij_niveau (kWh)": batterij_niveau
            })

        res = pd.DataFrame(resultaten)

        # === Nieuw: berekening vol/leer-tijd ===
        res["is_vol"] = res["batterij_niveau (kWh)"] >= soc_max - 1e-6
        res["is_leeg"] = res["batterij_niveau (kWh)"] <= soc_min + 1e-6

        tijd_vol_uren = res["is_vol"].sum() * kwartier_uur
        tijd_leeg_uren = res["is_leeg"].sum() * kwartier_uur
        tijd_totaal_uren = len(res) * kwartier_uur
        pct_vol = 100 * tijd_vol_uren / tijd_totaal_uren
        pct_leeg = 100 * tijd_leeg_uren / tijd_totaal_uren

        # Samenvatting berekenen
        besparing = (energie_zonder_batterij_van_net - energie_van_net) * prijs_import \
                    + (energie_naar_net - energie_zonder_batterij_naar_net) * prijs_export

        samenvatting = {
            "Energie geladen op batterij (kWh)": energie_op_batterij,
            "Energie gehaald van net (kWh)": energie_van_net,
            "Energie zonder batterij gehaald van net (kWh)": energie_zonder_batterij_van_net,
            "Energie teruggeleverd aan net (kWh)": energie_naar_net,
            "Energie zonder batterij teruggeleverd aan net (kWh)": energie_zonder_batterij_naar_net,
            "Eindsituatie batterij (kWh)": batterij_niveau,
            "Batterij vol (uren)": tijd_vol_uren,
            "Batterij leeg (uren)": tijd_leeg_uren,
            "Batterij vol (% van tijd)": f"{pct_vol:.1f}%",
            "Batterij leeg (% van tijd)": f"{pct_leeg:.1f}%",
            "Besparing (€)": besparing
        }

        st.success("✅ Simulatie voltooid!")

        # Tabs voor overzicht, grafieken en downloads
        tab1, tab2, tab3 = st.tabs(["📊 Overzicht", "📈 Grafieken", "📥 Downloads"])

        with tab1:
            st.subheader("📋 Samenvatting resultaten")
            st.table(pd.DataFrame(list(samenvatting.items()), columns=["Omschrijving", "Waarde"]))

            # Maandelijkse winstberekening
            res["maand"] = res["tijd"].dt.to_period("M")
            maand_energie_van_net = res.groupby("maand")["van_net (kWh)"].sum()
            maand_energie_naar_net = res.groupby("maand")["naar_net (kWh)"].sum()
            maand_zonder_van_net = df_kwartier.groupby(df_kwartier["datetime"].dt.to_period("M"))["afname"].sum()
            maand_zonder_naar_net = df_kwartier.groupby(df_kwartier["datetime"].dt.to_period("M"))["injectie"].sum()

            maand_winst = (maand_zonder_van_net - maand_energie_van_net) * prijs_import \
                        + (maand_energie_naar_net - maand_zonder_naar_net) * prijs_export

            maand_df = pd.DataFrame({
                "Maand": maand_winst.index.astype(str),
                "Winst (€)": maand_winst.values
            })

            st.subheader("💰 Maandelijkse besparing")
            st.dataframe(maand_df, use_container_width=True)

            fig_bar = px.bar(maand_df, x="Maand", y="Winst (€)", title="Maandelijkse winst door batterij", text_auto=True)
            st.plotly_chart(fig_bar, use_container_width=True)

        with tab2:
            st.subheader("🔋 Batterijniveau door de tijd")
            fig, ax = plt.subplots(figsize=(10,5))
            ax.fill_between(res["tijd"], res["batterij_niveau (kWh)"], color='green', alpha=0.3, label="Batterijniveau")
            ax.scatter(res["tijd"], res["opladen (kWh)"], color='blue', s=8, label="Opladen")
            ax.scatter(res["tijd"], res["ontladen (kWh)"], color='red', s=8, label="Ontladen")
            ax.axhline(soc_max, color='gray', linestyle='--', label="SoC max")
            ax.axhline(soc_min, color='gray', linestyle='--', label="SoC min")
            ax.set_xlabel("Tijd")
            ax.set_ylabel("kWh")
            ax.legend()
            ax.grid(True)
            st.pyplot(fig)

            st.subheader("⚡ Interactieve grafiek")
            fig_plotly = px.line(res, x="tijd", y=["van_net (kWh)", "naar_net (kWh)", "batterij_niveau (kWh)"],
                                 title="Energieverbruik en batterijniveau")
            st.plotly_chart(fig_plotly, use_container_width=True)

        with tab3:
            st.subheader("📥 Download resultaten")
            csv_res = res.to_csv(sep=';', index=False, decimal=',')
            csv_summary = pd.DataFrame(list(samenvatting.items()), columns=["Omschrijving", "Waarde"]).to_csv(sep=';', index=False, decimal=',')
            csv_maand = maand_df.to_csv(sep=';', index=False, decimal=',')

            st.download_button("⬇️ Gedetailleerde kwartiertabel (CSV)", csv_res, "simulatie_resultaten.csv", "text/csv")
            st.download_button("⬇️ Samenvatting (CSV)", csv_summary, "simulatie_samenvatting.csv", "text/csv")
            st.download_button("⬇️ Maandelijkse winst (CSV)", csv_maand, "simulatie_maandwinst.csv", "text/csv")

else:
    st.info("⬅️ Upload een CSV-bestand om te starten.")

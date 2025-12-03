#!/usr/bin/env python3
"""Analytics Dashboard for Phone Agent.

Run with: streamlit run scripts/dashboard.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Database connection
DATABASE_URL = os.environ.get(
    "ITF_DATABASE_URL", "sqlite:///./phone_agent.db"
).replace("+aiosqlite", "")  # Use sync driver


@st.cache_resource
def get_engine():
    """Get database engine."""
    return create_engine(DATABASE_URL)


@st.cache_data(ttl=60)
def load_calls_summary() -> pd.DataFrame:
    """Load calls summary by date."""
    engine = get_engine()
    query = """
    SELECT
        DATE(started_at) as date,
        COUNT(*) as total_calls,
        SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound,
        SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) as outbound,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'missed' THEN 1 ELSE 0 END) as missed,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        AVG(CASE WHEN status = 'completed' THEN duration_seconds ELSE NULL END) as avg_duration
    FROM calls
    GROUP BY DATE(started_at)
    ORDER BY date DESC
    LIMIT 60
    """
    return pd.read_sql(query, engine)


@st.cache_data(ttl=60)
def load_appointments_summary() -> pd.DataFrame:
    """Load appointments summary by date."""
    engine = get_engine()
    query = """
    SELECT
        appointment_date as date,
        COUNT(*) as total,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'no_show' THEN 1 ELSE 0 END) as no_show,
        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
        SUM(CASE WHEN status IN ('scheduled', 'confirmed') THEN 1 ELSE 0 END) as upcoming
    FROM appointments
    GROUP BY appointment_date
    ORDER BY date DESC
    LIMIT 60
    """
    return pd.read_sql(query, engine)


@st.cache_data(ttl=60)
def load_call_metrics() -> pd.DataFrame:
    """Load aggregated call metrics."""
    engine = get_engine()
    query = """
    SELECT
        date,
        total_calls,
        inbound_calls,
        outbound_calls,
        completed_calls,
        missed_calls,
        avg_duration,
        appointments_booked,
        completion_rate,
        appointment_conversion_rate,
        ai_resolution_rate
    FROM call_metrics
    WHERE hour IS NULL
    ORDER BY date DESC
    LIMIT 60
    """
    return pd.read_sql(query, engine)


@st.cache_data(ttl=60)
def load_contacts_stats() -> dict:
    """Load contact statistics."""
    engine = get_engine()

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM contacts WHERE is_deleted = 0")).scalar()
        by_type = pd.read_sql(
            "SELECT contact_type, COUNT(*) as count FROM contacts WHERE is_deleted = 0 GROUP BY contact_type",
            conn
        )
        by_industry = pd.read_sql(
            "SELECT industry, COUNT(*) as count FROM contacts WHERE is_deleted = 0 GROUP BY industry",
            conn
        )

    return {
        "total": total,
        "by_type": by_type,
        "by_industry": by_industry,
    }


@st.cache_data(ttl=60)
def load_campaigns() -> pd.DataFrame:
    """Load recall campaigns."""
    engine = get_engine()
    query = """
    SELECT
        name,
        campaign_type,
        status,
        start_date,
        end_date,
        total_contacts,
        contacts_called,
        contacts_reached,
        appointments_booked
    FROM recall_campaigns
    ORDER BY start_date DESC
    """
    return pd.read_sql(query, engine)


def render_kpi_card(title: str, value: str | int | float, delta: str | None = None):
    """Render a KPI card."""
    st.metric(label=title, value=value, delta=delta)


def main():
    """Main dashboard application."""
    st.set_page_config(
        page_title="Phone Agent Analytics",
        page_icon="📞",
        layout="wide",
    )

    st.title("📞 Phone Agent Analytics Dashboard")
    st.markdown("Real-time analytics for the AI Phone Agent system")

    # Sidebar filters
    st.sidebar.header("Filters")
    date_range = st.sidebar.selectbox(
        "Date Range",
        ["Last 7 days", "Last 30 days", "Last 60 days", "All time"],
        index=1,
    )

    # Load data
    calls_df = load_calls_summary()
    appointments_df = load_appointments_summary()
    metrics_df = load_call_metrics()
    contacts_stats = load_contacts_stats()
    campaigns_df = load_campaigns()

    # Apply date filter
    today = date.today()
    if date_range == "Last 7 days":
        cutoff = today - timedelta(days=7)
    elif date_range == "Last 30 days":
        cutoff = today - timedelta(days=30)
    elif date_range == "Last 60 days":
        cutoff = today - timedelta(days=60)
    else:
        cutoff = None

    if cutoff and not calls_df.empty:
        calls_df["date"] = pd.to_datetime(calls_df["date"]).dt.date
        calls_df = calls_df[calls_df["date"] >= cutoff]

    if cutoff and not appointments_df.empty:
        appointments_df["date"] = pd.to_datetime(appointments_df["date"]).dt.date
        appointments_df = appointments_df[appointments_df["date"] >= cutoff]

    if cutoff and not metrics_df.empty:
        metrics_df["date"] = pd.to_datetime(metrics_df["date"]).dt.date
        metrics_df = metrics_df[metrics_df["date"] >= cutoff]

    # =========================================================================
    # KPI Summary Row
    # =========================================================================
    st.header("Key Performance Indicators")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_calls = calls_df["total_calls"].sum() if not calls_df.empty else 0
        render_kpi_card("Total Calls", f"{total_calls:,}")

    with col2:
        if not calls_df.empty:
            completed = calls_df["completed"].sum()
            total = calls_df["total_calls"].sum()
            rate = (completed / total * 100) if total > 0 else 0
            render_kpi_card("Completion Rate", f"{rate:.1f}%")
        else:
            render_kpi_card("Completion Rate", "N/A")

    with col3:
        total_appts = appointments_df["total"].sum() if not appointments_df.empty else 0
        render_kpi_card("Appointments", f"{total_appts:,}")

    with col4:
        if not appointments_df.empty:
            no_shows = appointments_df["no_show"].sum()
            total = appointments_df["total"].sum()
            rate = (no_shows / total * 100) if total > 0 else 0
            render_kpi_card("No-Show Rate", f"{rate:.1f}%")
        else:
            render_kpi_card("No-Show Rate", "N/A")

    with col5:
        render_kpi_card("Total Contacts", f"{contacts_stats['total']:,}")

    # =========================================================================
    # Charts Row 1: Calls Over Time
    # =========================================================================
    st.header("Call Analytics")

    col1, col2 = st.columns(2)

    with col1:
        if not calls_df.empty:
            fig = px.line(
                calls_df.sort_values("date"),
                x="date",
                y="total_calls",
                title="Daily Call Volume",
                labels={"date": "Date", "total_calls": "Calls"},
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No call data available")

    with col2:
        if not calls_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Completed",
                x=calls_df.sort_values("date")["date"],
                y=calls_df.sort_values("date")["completed"],
                marker_color="green",
            ))
            fig.add_trace(go.Bar(
                name="Missed",
                x=calls_df.sort_values("date")["date"],
                y=calls_df.sort_values("date")["missed"],
                marker_color="orange",
            ))
            fig.add_trace(go.Bar(
                name="Failed",
                x=calls_df.sort_values("date")["date"],
                y=calls_df.sort_values("date")["failed"],
                marker_color="red",
            ))
            fig.update_layout(
                barmode="stack",
                title="Call Status Distribution",
                xaxis_title="Date",
                yaxis_title="Calls",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No call data available")

    # =========================================================================
    # Charts Row 2: Appointments
    # =========================================================================
    st.header("Appointment Analytics")

    col1, col2 = st.columns(2)

    with col1:
        if not appointments_df.empty:
            fig = px.area(
                appointments_df.sort_values("date"),
                x="date",
                y="total",
                title="Daily Appointments",
                labels={"date": "Date", "total": "Appointments"},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No appointment data available")

    with col2:
        if not appointments_df.empty:
            # Status distribution pie chart
            status_totals = {
                "Completed": appointments_df["completed"].sum(),
                "No-Show": appointments_df["no_show"].sum(),
                "Cancelled": appointments_df["cancelled"].sum(),
                "Upcoming": appointments_df["upcoming"].sum(),
            }
            fig = px.pie(
                values=list(status_totals.values()),
                names=list(status_totals.keys()),
                title="Appointment Status Distribution",
                color_discrete_sequence=["green", "red", "gray", "blue"],
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No appointment data available")

    # =========================================================================
    # Contacts Analysis
    # =========================================================================
    st.header("Contact Analytics")

    col1, col2 = st.columns(2)

    with col1:
        if not contacts_stats["by_type"].empty:
            fig = px.pie(
                contacts_stats["by_type"],
                values="count",
                names="contact_type",
                title="Contacts by Type",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No contact type data available")

    with col2:
        if not contacts_stats["by_industry"].empty:
            fig = px.bar(
                contacts_stats["by_industry"],
                x="industry",
                y="count",
                title="Contacts by Industry",
                labels={"industry": "Industry", "count": "Count"},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No contact industry data available")

    # =========================================================================
    # Campaigns Table
    # =========================================================================
    st.header("Recall Campaigns")

    if not campaigns_df.empty:
        # Calculate conversion rate
        campaigns_df["conversion_rate"] = (
            campaigns_df["appointments_booked"] / campaigns_df["contacts_reached"] * 100
        ).fillna(0).round(1)

        st.dataframe(
            campaigns_df[["name", "campaign_type", "status", "total_contacts",
                         "contacts_called", "contacts_reached", "appointments_booked",
                         "conversion_rate"]],
            use_container_width=True,
            column_config={
                "name": "Campaign Name",
                "campaign_type": "Type",
                "status": "Status",
                "total_contacts": "Total Contacts",
                "contacts_called": "Called",
                "contacts_reached": "Reached",
                "appointments_booked": "Appointments",
                "conversion_rate": st.column_config.NumberColumn(
                    "Conversion %",
                    format="%.1f%%",
                ),
            },
        )
    else:
        st.info("No campaign data available")

    # =========================================================================
    # AI Performance Metrics
    # =========================================================================
    if not metrics_df.empty:
        st.header("AI Performance Metrics")

        col1, col2, col3 = st.columns(3)

        with col1:
            avg_ai_rate = metrics_df["ai_resolution_rate"].mean() * 100
            render_kpi_card("AI Resolution Rate", f"{avg_ai_rate:.1f}%")

        with col2:
            avg_conversion = metrics_df["appointment_conversion_rate"].mean() * 100
            render_kpi_card("Appointment Conversion", f"{avg_conversion:.1f}%")

        with col3:
            avg_completion = metrics_df["completion_rate"].mean() * 100
            render_kpi_card("Call Completion", f"{avg_completion:.1f}%")

        fig = px.line(
            metrics_df.sort_values("date"),
            x="date",
            y=["ai_resolution_rate", "appointment_conversion_rate", "completion_rate"],
            title="Performance Metrics Over Time",
            labels={"date": "Date", "value": "Rate", "variable": "Metric"},
        )
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    # Footer
    st.markdown("---")
    st.markdown(
        "📊 Dashboard powered by **Streamlit** | Data from **Phone Agent SQLite DB**"
    )


if __name__ == "__main__":
    main()

"""
Enterprise NLP Intelligence System - Professional Application
Version 2.0.0
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
from datetime import datetime

from config import APP_NAME, APP_VERSION, APP_DESCRIPTION, DEFAULT_MODEL
from utils.auth import init_session, is_authenticated, get_current_user, get_current_user_id
from utils import database, ui
from utils.model_loader import load_model, predict
from utils import analytics


# ============ PAGE CONFIG ============
st.set_page_config(
    page_title=f"{APP_NAME} - {APP_VERSION}",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize app state
if "app_name" not in st.session_state:
    st.session_state.app_name = APP_NAME

# Initialize database
database.init_database()

# Load custom CSS
ui.load_css()

# Initialize session
init_session()


# ============ AUTHENTICATION FLOW ============
if not is_authenticated():
    ui.login_page()
    st.stop()


# ============ AUTHENTICATED APP ============
current_user = get_current_user()
current_user_id = get_current_user_id()

# Render header and sidebar
ui.header_bar(current_user)
page = ui.sidebar_nav(current_user)


# ============ DASHBOARD PAGE ============
def dashboard_page():
    """Dashboard with overview and quick stats."""
    ui.hero_section()
    
    # Get user analytics
    user_analytics = database.get_user_analytics(current_user_id)
    
    # Render metric cards
    ui.metric_cards(
        user_analytics['total_predictions'],
        user_analytics['average_confidence'],
        user_analytics['most_used_label']
    )
    
    # Recent predictions
    st.markdown("### 📋 Recent Predictions")
    predictions = database.get_user_predictions(current_user_id, limit=5)
    
    if predictions:
        df = pd.DataFrame(predictions)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                'created_at': st.column_config.TextColumn('Date'),
                'text': st.column_config.TextColumn('Text', width='large'),
                'label': st.column_config.TextColumn('Label'),
                'confidence': st.column_config.NumberColumn('Confidence', format='%.3f'),
            }
        )
    else:
        st.info("No predictions yet. Start classifying text in the Classifier section!")
    
    # Quick insights
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Accuracy Trend")
        if len(predictions) > 1:
            trend_data = pd.DataFrame({
                'confidence': [p['confidence'] for p in predictions[::-1]],
                'index': range(len(predictions[::-1]))
            })
            fig = px.line(trend_data, x='index', y='confidence', 
                         title='Confidence Over Time',
                         markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need more predictions to show trend")
    
    with col2:
        st.markdown("### 🏷️ Label Distribution")
        if predictions:
            label_data = pd.DataFrame(predictions)
            label_counts = label_data['label'].value_counts()
            fig = px.pie(values=label_counts.values, names=label_counts.index,
                        title='Label Distribution')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Labels will appear after predictions")


# ============ CLASSIFIER PAGE ============
def classifier_page():
    """Zero-shot text classification interface."""
    st.header("🤖 Zero-Shot Text Classifier")
    
    ui.info_box(
        "How it Works",
        "Enter your text and candidate labels. The model will classify the text into one of your categories with confidence scores."
    )
    
    # Classification form
    with st.form("classify_form", border=False):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            text = st.text_area(
                "📝 Enter text to classify",
                height=200,
                placeholder="Paste your text here...",
                help="Maximum 5000 characters"
            )
        
        with col2:
            st.markdown("### ⚙️ Configuration")
            labels = st.text_input(
                "🏷️ Candidate labels",
                value="business,technical,marketing,hr,finance",
                help="Comma-separated list of categories"
            )
            multi_label = st.checkbox("Allow multi-label predictions", value=True)
            confidence_threshold = st.slider(
                "Minimum confidence",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.1
            )
            submitted = st.form_submit_button(
                "🚀 Classify Text",
                use_container_width=True,
                type="primary"
            )
        
        if submitted:
            if not text.strip():
                ui.error_message("Validation Error", "Please provide text to classify.")
                return
            
            if not labels.strip():
                ui.error_message("Validation Error", "Please provide candidate labels.")
                return
            
            candidate_labels = [l.strip() for l in labels.split(",") if l.strip()]
            
            try:
                with st.spinner("⏳ Loading model..."):
                    model = load_model()
                
                with st.spinner("🔄 Running inference..."):
                    results = predict(model, text, candidate_labels, multi_label=multi_label)
                
                # Save to database
                database.save_prediction(
                    current_user_id,
                    text,
                    results['labels'][0] if results['labels'] else 'Unknown',
                    results['scores'][0] if results['scores'] else 0.0,
                    json.dumps(results['labels']),
                    json.dumps(results['scores'])
                )
                
                ui.success_message("Classification Complete", "Text classified successfully!")
                
                # Display results
                st.markdown("### 📊 Classification Results")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    ui.result_visualization(results['labels'], results['scores'])
                
                with col2:
                    # Summary
                    st.markdown("### 📈 Summary")
                    st.metric("Top Label", results['labels'][0] if results['labels'] else "N/A")
                    st.metric("Confidence", f"{results['scores'][0]:.2%}" if results['scores'] else "N/A")
                    
                    # Export option
                    csv_data = pd.DataFrame({
                        "text": [text],
                        "label": [results['labels'][0] if results['labels'] else ''],
                        "score": [results['scores'][0] if results['scores'] else 0.0]
                    }).to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="📥 Download Result",
                        data=csv_data,
                        file_name=f"prediction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )
            
            except Exception as e:
                ui.error_message("Classification Error", f"An error occurred: {str(e)}")
    
    # Batch processing section
    st.markdown("---")
    st.markdown("### 📦 Batch CSV Processing")
    
    ui.info_box(
        "Batch Processing",
        "Upload a CSV file with a 'text' column to classify multiple records at once."
    )
    
    uploaded_file = st.file_uploader(
        "Upload CSV file",
        type=['csv'],
        help="CSV file must contain a column with 'text' in the name"
    )
    
    if uploaded_file is not None:
        df_input = pd.read_csv(uploaded_file)
        text_cols = [c for c in df_input.columns if 'text' in c.lower()]
        
        if not text_cols:
            ui.error_message("Format Error", "CSV must have a column with 'text' in the name")
        else:
            text_col = text_cols[0]
            st.info(f"Using column: **{text_col}** ({len(df_input)} rows)")
            
            if st.button("🚀 Process Batch", key="batch_process"):
                try:
                    model = load_model()
                    batch_labels = st.text_input(
                        "Labels for batch processing",
                        value="business,technical,marketing,hr,finance",
                        key="batch_labels"
                    )
                    candidate_labels = [l.strip() for l in batch_labels.split(",") if l.strip()]
                    
                    progress_bar = st.progress(0)
                    results_list = []
                    
                    for i, text in enumerate(df_input[text_col].astype(str).tolist()):
                        result = predict(model, text, candidate_labels, multi_label=True)
                        database.save_prediction(
                            current_user_id,
                            text,
                            result['labels'][0] if result['labels'] else 'Unknown',
                            result['scores'][0] if result['scores'] else 0.0,
                            json.dumps(result['labels']),
                            json.dumps(result['scores'])
                        )
                        results_list.append({
                            'original_text': text,
                            'predicted_label': result['labels'][0] if result['labels'] else '',
                            'confidence': result['scores'][0] if result['scores'] else 0.0
                        })
                        progress_bar.progress((i + 1) / len(df_input))
                    
                    # Display results
                    results_df = pd.DataFrame(results_list)
                    st.dataframe(results_df, use_container_width=True, hide_index=True)
                    
                    # Export batch results
                    csv_export = results_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Batch Results",
                        data=csv_export,
                        file_name=f"batch_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime='text/csv'
                    )
                    
                    ui.success_message("Batch Processing Complete", f"Successfully processed {len(results_list)} predictions")
                except Exception as e:
                    ui.error_message("Batch Error", f"Error processing batch: {str(e)}")


# ============ ANALYTICS PAGE ============
def analytics_page():
    """Analytics and insights dashboard."""
    st.header("📈 Advanced Analytics")
    
    user_analytics = database.get_user_analytics(current_user_id)
    predictions = database.get_user_predictions(current_user_id, limit=1000)
    
    if not predictions:
        st.info("No predictions yet. Start classifying to see analytics!")
        return
    
    df = pd.DataFrame(predictions)
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Predictions", len(predictions))
    with col2:
        st.metric("Avg Confidence", f"{user_analytics['average_confidence']:.2%}")
    with col3:
        st.metric("High Confidence (>0.8)", len(df[df['confidence'] > 0.8]))
    with col4:
        st.metric("Date Range", f"{len(df)} items")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Confidence Distribution")
        fig_hist = px.histogram(df, x='confidence', nbins=20, title='Confidence Score Distribution')
        st.plotly_chart(fig_hist, use_container_width=True)
    
    with col2:
        st.markdown("### 🏷️ Top Labels")
        top_labels = df['label'].value_counts().head(10)
        fig_bar = px.bar(x=top_labels.values, y=top_labels.index, orientation='h', title='Top 10 Labels')
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # Timeline
    st.markdown("### 📅 Prediction Timeline")
    df['date'] = pd.to_datetime(df['created_at']).dt.date
    daily_count = df.groupby('date').size()
    fig_line = px.line(x=daily_count.index, y=daily_count.values, title='Predictions Over Time')
    st.plotly_chart(fig_line, use_container_width=True)
    
    # Data export
    st.markdown("---")
    st.markdown("### 📥 Export Data")
    
    col1, col2 = st.columns(2)
    with col1:
        csv_data = database.export_user_data(current_user_id)
        st.download_button(
            label="📥 Download All Predictions (CSV)",
            data=csv_data,
            file_name=f"all_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime='text/csv'
        )
    
    with col2:
        json_data = df.to_json(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download All Predictions (JSON)",
            data=json_data,
            file_name=f"all_predictions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime='application/json'
        )


# ============ SETTINGS PAGE ============
def settings_page():
    """User settings and preferences."""
    st.header("⚙️ Settings")
    
    # Get user info
    user_info = database.get_user_info(current_user)
    
    st.markdown("### 👤 Profile Information")
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Username", current_user)
    with col2:
        st.metric("User ID", current_user_id)
    
    st.markdown(f"📧 **Email:** {user_info['email']}")
    st.markdown(f"👤 **Full Name:** {user_info['full_name'] or 'Not set'}")
    st.markdown(f"📅 **Member Since:** {user_info['created_at']}")
    
    if user_info['last_login']:
        st.markdown(f"🔓 **Last Login:** {user_info['last_login']}")
    
    st.markdown("---")
    
    st.markdown("### 📊 Model Information")
    st.markdown(f"**Model:** {DEFAULT_MODEL}")
    st.markdown(f"**Architecture:** DistilBERT (MNLI)")
    st.markdown(f"**Type:** Zero-shot Classification")
    st.markdown(f"**Framework:** HuggingFace Transformers")
    
    st.markdown("---")
    
    st.markdown("### 🗑️ Danger Zone")
    
    if st.button("🗑️ Delete All Predictions", key="delete_all"):
        st.warning("This action cannot be undone!")
        if st.button("⚠️ Confirm Delete All", key="confirm_delete"):
            # Delete all predictions
            predictions = database.get_user_predictions(current_user_id, limit=10000)
            for pred in predictions:
                database.delete_prediction(pred['id'], current_user_id)
            st.success("All predictions deleted!")
            st.rerun()
    
    st.markdown("---")
    st.markdown("### ℹ️ Application Info")
    st.markdown(f"**App Name:** {APP_NAME}")
    st.markdown(f"**Version:** {APP_VERSION}")
    st.markdown(f"**Description:** {APP_DESCRIPTION}")


# ============ HELP PAGE ============
def help_page():
    """Help and documentation."""
    st.header("📖 Help & Documentation")
    
    st.markdown("### 🎯 Getting Started")
    st.markdown("""
    1. **Login or Sign Up:** Create your account or log in with existing credentials
    2. **Navigate to Classifier:** Go to the Classifier section to start
    3. **Enter Text:** Paste or type your text to classify
    4. **Set Labels:** Define the categories you want to classify into
    5. **Get Results:** View confidence scores for each label
    """)
    
    st.markdown("### 💡 Features")
    st.markdown("""
    - **Single Text Classification:** Classify individual texts with instant results
    - **Batch Processing:** Upload CSV files to classify multiple texts at once
    - **Multi-label Support:** Classify texts into multiple categories
    - **Advanced Analytics:** Track patterns and trends in your predictions
    - **Data Export:** Download your predictions in CSV or JSON format
    - **Secure Storage:** All your data is securely stored in the database
    """)
    
    st.markdown("### ❓ FAQ")
    
    with st.expander("What is zero-shot classification?"):
        st.markdown("""
        Zero-shot classification allows you to classify text into categories without training data.
        The model uses natural language understanding to match text to categories you define,
        making it flexible for custom use cases.
        """)
    
    with st.expander("What's the maximum text length?"):
        st.markdown("The model can handle texts up to 5000 characters. Longer texts will be truncated.")
    
    with st.expander("Can I use custom models?"):
        st.markdown("""
        Currently, the app uses the distilbert-base-uncased-mnli model.
        Custom model support will be added in future versions.
        """)
    
    with st.expander("How accurate are the predictions?"):
        st.markdown("""
        Accuracy depends on several factors:
        - Quality of your text
        - How well your labels describe the categories
        - Model confidence threshold
        
        Check your analytics to track accuracy trends.
        """)
    
    with st.expander("How do I export my data?"):
        st.markdown("""
        Visit the Analytics page to download all your predictions in CSV or JSON format.
        Individual predictions can also be downloaded from the Classifier page.
        """)
    
    st.markdown("### 🔗 Resources")
    st.markdown("""
    - [HuggingFace Models](https://huggingface.co/models)
    - [Zero-shot Classification Guide](https://huggingface.co/tasks/zero-shot-classification)
    - [Streamlit Documentation](https://docs.streamlit.io)
    """)
    
    st.markdown("### 📞 Support")
    st.markdown("For issues or questions, contact the development team.")


# ============ PAGE ROUTING ============
if page == "📊 Dashboard":
    dashboard_page()
elif page == "🤖 Classifier":
    classifier_page()
elif page == "📈 Analytics":
    analytics_page()
elif page == "⚙️ Settings":
    settings_page()
elif page == "📖 Help":
    help_page()


# ============ FOOTER ============
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #CBD5E1; font-size: 0.85rem;'>
        <p>🚀 Enterprise NLP Intelligence v{APP_VERSION} | 
        <span style='color: #00D9FF;'>Powered by HuggingFace Transformers & Streamlit</span></p>
    </div>
    """,
    unsafe_allow_html=True
)
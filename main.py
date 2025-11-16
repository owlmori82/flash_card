import streamlit as st
import pandas as pd
import datetime
import os
from supabase import create_client, Client
from st_supabase_connection import SupabaseConnection
import uuid
import hashlib


# ====== Browser TTS 関数（追加） ======
def browser_tts(text: str):
    """ブラウザ側 SpeechSynthesis で英文を読み上げる"""
    escaped = text.replace('"', '\\"')
    tts_js = f"""
        <script>
            var msg = new SpeechSynthesisUtterance("{escaped}");
            msg.lang = "en-US";
            window.speechSynthesis.speak(msg);
        </script>
    """
    st.markdown(tts_js, unsafe_allow_html=True)


# データを読み込む関数
def load_data(conn,TABLE_NAME):
    response = conn.table(TABLE_NAME).select("*").execute()
    df = pd.DataFrame(data = response.data)
    df["LastAsked"] = pd.to_datetime(df["LastAsked"], format="ISO8601")
    return df

# データを保存する関数
def save_data(df,conn,TABLE_NAME):
    df_tmp = df.copy()
    df_tmp["LastAsked"] = df_tmp["LastAsked"].astype(str)
    df_tmp = df_tmp.astype({
        "id":"int64",
        "Japanese": "string",
        "English": "string",
        "Correct": "int64",
        "Incorrect": "int64",
        "LastAsked": "string"
    })
    for _, row in df_tmp.iterrows():
        conn.table(TABLE_NAME).upsert(row.to_dict()).execute()

# 優先出題条件に基づきデータをフィルタリング
def filter_questions(df):
    today = datetime.datetime.now()
    df["DaysSinceLastAsked"] = df["LastAsked"].apply(
        lambda x: (today - pd.to_datetime(x)).days if pd.notnull(x) else float("inf")
    )
    df["Accuracy"] = df["Correct"] / (df["Correct"] + df["Incorrect"])
    df["Accuracy"] = df["Accuracy"].fillna(0)

    group_a = df[df["Correct"] + df["Incorrect"] == 0].sort_values(by="LastAsked", na_position="first")
    group_b = df[(df["Correct"] + df["Incorrect"] == 1) & (df["DaysSinceLastAsked"] >= 1)]
    group_c = df[(df["Correct"] + df["Incorrect"] == 2) & (df["DaysSinceLastAsked"] >= 3)]
    group_d = df[(df["Correct"] + df["Incorrect"] == 3) & (df["DaysSinceLastAsked"] >= 7)]
    group_e = df[(df["Correct"] + df["Incorrect"] >= 4) & (df["Accuracy"] < 0.8)]

    selected_a = group_a.head(5)
    selected_b = group_b.head(5)
    selected_c = group_c.head(5)
    selected_d = group_d.head(5)
    selected_e = group_e.sample(n=min(5, len(group_e))) if len(group_e) > 0 else pd.DataFrame()

    selected = pd.concat([selected_a, selected_b, selected_c, selected_d, selected_e])
    remaining = df.loc[~df.index.isin(selected.index)]

    final_result = pd.concat([selected, remaining]).reset_index(drop=True)
    final_result = final_result.drop(columns=["DaysSinceLastAsked", "Accuracy"])
    return final_result

#回答結果を更新
def update_data(rec,df):
    df = df.astype(str)
    update_row = pd.DataFrame(rec,index = rec.index).T.astype(str)
    df = pd.concat([df,update_row])
    return df

#終了処理
def fin_process(update_rows,conn_point,table_name,count):
    st.write("回答数：",count)
    save_data(update_rows,conn_point,table_name)
    st.success("記録を保存しました！お疲れ様でした。")
    st.stop()

# === ページ1：復習問題出題 ===
def page_quiz(conn, TABLE_NAME):
    st.title("Flash Card Quiz")
    
    #初期化
    if "read_file" not in st.session_state:
        st.session_state.read_file = False
    if "data" not in st.session_state:
        st.session_state.data = None
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "update_df" not in st.session_state:
        st.session_state.update_df = pd.DataFrame(columns=['id','Japanese','English','Correct','Incorrect','LastAsked'])
    if "repair_question" not in st.session_state:
        st.session_state.repair_question = "empty"
                     
    #データベースから取得
    if st.session_state.read_file == False:
        st.session_state.data = load_data(conn,TABLE_NAME)
        st.session_state.data = filter_questions(st.session_state.data)
        st.session_state.read_file = True
        
    if st.session_state.current_index < len(st.session_state.data):
        current_question = st.session_state.data.iloc[st.session_state.current_index]
        st.write(f"**問題:** {current_question['Japanese']}")
        st.write(f"--現在の回答数:-- **{st.session_state.current_index} 回**")

        # 答えを見る
        if "show_answer" not in st.session_state:
            st.session_state.show_answer = False

        if st.button("答えを見る"):
            st.session_state.show_answer = True

        if st.session_state.show_answer:
            st.write(f"**答え:** {current_question['English']}")

            # === ここを Browser TTS へ変更 ===
            if st.button("🔊 音声を再生"):
                browser_tts(current_question['English'])

            #問題文の訂正
            if st.session_state.repair_question == "empty":
                st.write("---------------------------------")
                repair = st.text_input("問題文の訂正")
                if st.button("訂正"):
                    st.session_state.repair_question = repair
                st.write("---------------------------------")
            
            # 正解
            if st.button("正解"):
                current_question["Correct"] += 1
                current_question["LastAsked"] = datetime.datetime.now()

                if st.session_state.repair_question != "empty":
                    current_question['Japanese'] = st.session_state.repair_question
                    st.session_state.repair_question = "empty"

                st.session_state.update_df = update_data(current_question,st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()

            # 不正解
            if st.button("不正解"):
                current_question["Incorrect"] += 1
                current_question["LastAsked"] = datetime.datetime.now()

                if st.session_state.repair_question != "empty":
                    current_question['Japanese'] = st.session_state.repair_question
                    st.session_state.repair_question = "empty"

                st.session_state.update_df = update_data(current_question,st.session_state.update_df)
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()
    else:
        st.write("すべての問題が終了しました！")
        fin_process(st.session_state.update_df,conn,TABLE_NAME,st.session_state.current_index)
    
    #終了ボタン
    if st.button("終了"):
        fin_process(st.session_state.update_df,conn,TABLE_NAME,st.session_state.current_index)
        
    st.write("--------メンテナンス----------------")
    
    uploaded_file = st.file_uploader("データを更新するときはファイルをアップロードしてください", type=["csv"])
    
    if uploaded_file is not None:
        upf = pd.read_csv(uploaded_file)
        save_data(upf,conn,TABLE_NAME)
        st.success("ファイルがアップロードされ、データが更新されました。")
        
    st.download_button(
        label="結果をダウンロード",
        data=st.session_state.data.to_csv(index=False).encode("utf-8"),
        file_name="download_wordcards.csv",
        mime="text/csv"
    )

# === ページ2：新規問題の登録 ===
def page_register(conn, TABLE_NAME):
    st.title("新しい問題の登録")

    def get_next_id():
        existing_data = load_data(conn, TABLE_NAME)
        if existing_data.empty:
            return 1
        else:
            existing_ids = pd.to_numeric(existing_data["id"], errors="coerce")
            return int(existing_ids.max()) + 1

    if "next_id" not in st.session_state:
        st.session_state.next_id = get_next_id()

    next_id = st.session_state.next_id
    st.info(f"この問題のIDは `{next_id}` に自動設定されます。")
    
    if "form_key" not in st.session_state:
        st.session_state.form_key = str(uuid.uuid4())
    form_key = st.session_state.form_key

    exercise = st.text_area("日本語（必須）", key=f"exercise_{form_key}")
    answer = st.text_area("英語（必須）", key=f"answer_{form_key}")

    if st.button("この内容で問題を登録"):
        if exercise and answer:
            new_question = {
                "id": str(next_id),
                "Japanese": exercise,
                "English": answer,
                "Correct": 0,
                "Incorrect": 0,
                "LastAsked": datetime.datetime.now().isoformat()
            }
            conn.table(TABLE_NAME).insert(new_question).execute()
            st.success("新しい問題が登録されました！")
            st.session_state.clear()
            st.rerun()
        else:
            st.error("日本語、英語は必須です。")

# === メインアプリ ===
def main():
    conn = st.connection("supabase", type=SupabaseConnection)
    TABLE_NAME = 'wordcards'

    page = st.sidebar.selectbox("ページを選択", ["問題出題", "問題登録"])

    if page == "問題出題":
        page_quiz(conn, TABLE_NAME)
    elif page == "問題登録":
        page_register(conn, TABLE_NAME)

if __name__ == "__main__":
    main()

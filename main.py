import streamlit as st
import pandas as pd
import datetime
import os

# データを読み込む関数
def load_data(file_name):
    if os.path.exists(file_name):
        return pd.read_csv(file_name, parse_dates=["LastAsked"])
    else:
        # データが存在しない場合、初期データフレームを返す
        return pd.DataFrame(columns=["Japanese", "English", "Correct", "Incorrect", "LastAsked"])

# データを保存する関数
def save_data(df, file_name):
    df.to_csv(file_name, index=False)

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

# Streamlitアプリ
def main():
    st.title("Flash Card Quiz")
    uploaded_file = st.file_uploader("ファイルをアップロードしてください（例: flash_card.csv）", type=["csv"])
    data_path = "./data/flash_card.csv"
    if uploaded_file is not None:
        st.success("ファイルがアップロードされました。")
        df = uploaded_file
    else:
        st.info("デフォルトのファイル (./data/flash_card.csv) を使用します。")
        try:
            df = load_data(data_path)
        except FileNotFoundError:
            st.error("デフォルトのファイルが見つかりません。アプリを終了します。")
            st.stop()
    
    # セッション状態を初期化
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
        df = filter_questions(df)  # 最初に問題をフィルタリング
        save_data(df, data_path)  # フィルタリング結果を保存
        st.session_state.filtered_df = df

    # フィルタリング後のデータを取得
    df = st.session_state.filtered_df

    if st.session_state.current_index < len(df):
        # 現在の問題を取得
        current_question = df.iloc[st.session_state.current_index]
        st.write(f"**問題:** {current_question['Japanese']}")

        # 答えを見るボタン
        if "show_answer" not in st.session_state:
            st.session_state.show_answer = False

        if st.button("答えを見る"):
            st.session_state.show_answer = True

        if st.session_state.show_answer:
            st.write(f"**答え:** {current_question['English']}")

            # 正解ボタン
            if st.button("正解"):
                df.loc[st.session_state.current_index, "Correct"] += 1
                df.loc[st.session_state.current_index, "LastAsked"] = datetime.datetime.now()
                save_data(df, data_path)  # データを保存
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()

            # 不正解ボタン
            if st.button("不正解"):
                df.loc[st.session_state.current_index, "Incorrect"] += 1
                df.loc[st.session_state.current_index, "LastAsked"] = datetime.datetime.now()
                save_data(df, data_path)  # データを保存
                st.session_state.current_index += 1
                st.session_state.show_answer = False
                st.rerun()
    else:
        st.write("すべての問題が終了しました！")
    st.write("----------終了する前にダウンロードする-------------------------")
     # ダウンロードボタンを追加
    st.download_button(
        label="結果をダウンロード",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="updated_flash_card.csv",
        mime="text/csv"
    )
    #終了ボタン
    if st.button("終了"):
       save_data(df, data_path)
       st.success("記録を保存しました！お疲れ様でした。")
       st.stop()
       
if __name__ == "__main__":
    main()

import requests
import pandas as pd
from logger_config import logger

def fetch_fear_and_greed_index(limit: int = 0) -> pd.DataFrame:
    """
    Busca o índice "Fear & Greed" da API do alternative.me.

    Args:
        limit (int): Número de resultados a serem retornados. 0 para todos os dados históricos.

    Returns:
        pd.DataFrame: DataFrame com o índice "Fear & Greed", indexado por data.
                      Retorna um DataFrame vazio em caso de erro.
    """
    url = f"https://api.alternative.me/fng/?limit={limit}"
    try:
        logger.info(f"Buscando dados do Fear & Greed Index de {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json().get('data', [])

        if not data:
            logger.warning("Nenhum dado de Fear & Greed foi retornado pela API.")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df['value'] = pd.to_numeric(df['value'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.set_index('timestamp')
        df = df.rename(columns={'value': 'fng_value', 'value_classification': 'fng_classification'})

        logger.info(f"{len(df)} registros do Fear & Greed Index foram buscados com sucesso.")
        return df[['fng_value', 'fng_classification']]

    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar dados do Fear & Greed Index: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Erro inesperado ao processar dados do Fear & Greed Index: {e}")
        return pd.DataFrame()

if __name__ == '__main__':
    # Exemplo de uso
    fng_data = fetch_fear_and_greed_index(limit=30)
    if not fng_data.empty:
        print("Últimos 30 dias de dados do Fear & Greed Index:")
        print(fng_data.head())
        print("\nInfo do DataFrame:")
        fng_data.info()

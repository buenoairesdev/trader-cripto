import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import numpy as np # <--- ADICIONE ESTA LINHA


# --------------------------------------------------------------------------
# Função OTIMIZADA para Buscar Dados Kline (OHLCV) da Bybit API v5 (Paralela)
# --------------------------------------------------------------------------

def _parse_interval_to_milliseconds(interval: str) -> int:
    """Converte o string de intervalo da Bybit para milissegundos."""
    unit = interval[-1].upper()
    value = int(interval[:-1]) if len(interval) > 1 else 1 # Ex: '1', '5', '60', 'D'
    if interval.isdigit(): # Intervalos em minutos
        return int(interval) * 60 * 1000
    elif unit == 'D':
        return value * 24 * 60 * 60 * 1000
    elif unit == 'W':
        return value * 7 * 24 * 60 * 60 * 1000
    elif unit == 'M': # Aproximação para Mês
        return value * 30 * 24 * 60 * 60 * 1000
    else: # Assume minutos se não for D, W, M (ex: 120, 240)
         return value * 60 * 1000


def _fetch_single_chunk(category: str, symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1000) -> list:
    """Busca um único lote de dados kline para um período específico."""
    base_url = "https://api.bybit.com"
    kline_endpoint = "/v5/market/kline"
    url = base_url + kline_endpoint
    params = {
        'category': category,
        'symbol': symbol,
        'interval': interval,
        'start': start_time,
        'end': end_time,
        'limit': limit,
    }
    max_retries = 2 # Tentativas por chunk
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(url, params=params, timeout=15) # Timeout maior
            response.raise_for_status()
            data = response.json()
            if data.get('retCode') == 0 and data.get('result') and data['result'].get('list'):
                # Bybit retorna do mais antigo para o mais novo neste caso
                return data['result']['list']
            elif data.get('retCode') == 10006: # Rate limit error specific code
                 print(f"  Aviso: Rate limit atingido no chunk ({start_time}-{end_time}). Tentando novamente após espera...")
                 time.sleep(1.5 * (retries + 1)) # Espera mais longa para rate limit
            else:
                print(f"  Erro API Bybit no chunk ({start_time}-{end_time}): {data.get('retCode')} - {data.get('retMsg')}")
                return [] # Retorna vazio em caso de erro não recuperável
        except requests.exceptions.Timeout:
            print(f"  Timeout no chunk ({start_time}-{end_time}). Tentativa {retries+1}...")
            time.sleep(0.5 * (retries+1))
        except requests.exceptions.RequestException as e:
            print(f"  Erro HTTP no chunk ({start_time}-{end_time}): {e}")
            time.sleep(0.5 * (retries+1))
        except Exception as e:
            print(f"  Erro inesperado no chunk ({start_time}-{end_time}): {e}")
            return []
        retries += 1
    print(f"  Falha ao buscar chunk ({start_time}-{end_time}) após {max_retries} tentativas.")
    return []


def fetch_bybit_kline(
    category: str = 'linear',
    symbol: str = 'BTCUSDT',
    interval: str = '60',
    start_time_dt: datetime = None,
    end_time_dt: datetime = None,
    limit_per_request: int = 1000, # Máximo da API Bybit V5
    max_workers: int = 8         # Número de chamadas paralelas (ajuste com cuidado!)
) -> pd.DataFrame:
    """
    Busca dados históricos de klines (candlesticks) da API v5 da Bybit de forma otimizada (paralela).

    Args:
        category (str): Categoria ('spot', 'linear', 'inverse').
        symbol (str): Símbolo do par.
        interval (str): Intervalo ('1', '5', '60', 'D', etc.).
        start_time_dt (datetime): Data/hora inicial (timezone-aware). Se None, busca o máximo possível para trás.
        end_time_dt (datetime): Data/hora final (timezone-aware). Se None, usa a hora atual.
        limit_per_request (int): Limite por chamada API (máx 1000).
        max_workers (int): Número de requisições paralelas. Cuidado com rate limits!

    Returns:
        pd.DataFrame: DataFrame com OHLCV indexado por timestamp (UTC). Vazio em caso de erro.
    """
    if end_time_dt is None:
        end_time_dt = datetime.now(timezone.utc)
    if start_time_dt is None:
        # Se não há data de início, buscar o máximo possível pode ser complexo com paralelismo.
        # Por simplicidade, vamos exigir uma data de início por agora.
        # Ou definir um padrão, ex: 30 dias atrás.
        raise ValueError("A data de início (start_time_dt) é necessária para a busca paralela.")
        # start_time_dt = end_time_dt - timedelta(days=30) # Alternativa: padrão de 30 dias

    end_time_ms = int(end_time_dt.timestamp() * 1000)
    start_time_ms = int(start_time_dt.timestamp() * 1000)

    interval_ms = _parse_interval_to_milliseconds(interval)
    if interval_ms == 0:
        raise ValueError(f"Intervalo inválido: {interval}")

    # --- Calcular os Chunks (períodos) para buscar em paralelo ---
    chunks = []
    current_start = start_time_ms
    while current_start < end_time_ms:
        # Calcula o fim deste chunk baseado no limite e intervalo
        # Adiciona uma pequena margem para garantir cobertura
        current_end = min(current_start + limit_per_request * interval_ms -1 , end_time_ms) # Não exceder o fim total
        chunks.append((current_start, current_end))
        # O próximo chunk começa logo após o fim teórico deste lote
        current_start += limit_per_request * interval_ms

    print(f"Buscando dados para {symbol} ({interval}) de {start_time_dt} a {end_time_dt}")
    print(f"Dividido em {len(chunks)} chunks para busca paralela com até {max_workers} workers.")

    all_data_list = []
    futures = []

    # --- Usar ThreadPoolExecutor para buscar chunks em paralelo ---
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for start, end in chunks:
            # Submete a tarefa: chamar _fetch_single_chunk com os parâmetros
            future = executor.submit(
                _fetch_single_chunk,
                category, symbol, interval, start, end, limit_per_request
            )
            futures.append(future)

        # --- Coletar resultados conforme completam ---
        completed_count = 0
        for future in as_completed(futures):
            try:
                result_chunk = future.result() # Pega o resultado da thread (lista de klines)
                if result_chunk:
                    all_data_list.extend(result_chunk)
                completed_count += 1
                print(f"  Progresso: {completed_count}/{len(chunks)} chunks concluídos.", end='\r') # Mostra progresso
            except Exception as e:
                print(f"\n  Erro ao processar futuro de um chunk: {e}")

    print(f"\nBusca paralela concluída. {len(all_data_list)} velas brutas recebidas.") # Nova linha após progresso

    if not all_data_list:
        print("Nenhum dado foi retornado pela API.")
        return pd.DataFrame()

    # --- Processar e limpar os dados combinados ---
    df = pd.DataFrame(all_data_list, columns=[
        'timestamp_ms', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])
    # Remover duplicatas que podem surgir nas bordas dos chunks
    df = df.drop_duplicates(subset=['timestamp_ms'])

    # Conversões e Limpeza (igual à versão anterior, com correção do Future Warning)
    df['timestamp_ms'] = pd.to_numeric(df['timestamp_ms'], errors='coerce')
    df = df.dropna(subset=['timestamp_ms'])
    df['timestamp_ms'] = df['timestamp_ms'].astype(np.int64) # Usar np.int64

    df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms', utc=True)
    df = df.drop(columns=['timestamp_ms', 'turnover'])
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    df = df.dropna()

    # Ordenar pelo timestamp (essencial após busca paralela)
    df = df.sort_values(by='timestamp')

    # Filtrar novamente pelo range exato, pois os chunks podem exceder um pouco
    df = df[(df['timestamp'] >= start_time_dt) & (df['timestamp'] <= end_time_dt)]

    df = df.set_index('timestamp')

    print(f"Total de {len(df)} velas retornadas e processadas.")
    return df[['open', 'high', 'low', 'close', 'volume']]
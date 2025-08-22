# bybit_trade_manager.py
import pybit
from pybit.unified_trading import HTTP
import os
import time
from datetime import datetime
import json
import traceback # Para logar exceções completas
from dotenv import load_dotenv

# --- DEFINIÇÃO GLOBAL DO CAMINHO DO ARQUIVO JSON ---
# Esta variável agora é global e acessível em todo o script.
SCRIPT_DIR_BTM = os.path.dirname(os.path.abspath(__file__))
BYBIT_POSITIONS_JSON_FILE = os.path.join(SCRIPT_DIR_BTM, 'bybit_positions.json')
# --- FIM DA DEFINIÇÃO GLOBAL ---

TRADE_CATEGORY = 'linear' # Categoria de trading para futuros lineares (USDT)

class BybitTradeManager:
    """
    Gerencia a interação com a API de Trading da Bybit para execução de ordens.
    Utiliza o SDK pybit.
    """
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, category: str = 'linear'):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category
        
        self.client = HTTP(
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret,
            timeout=10,
        )
        print(f"BybitTradeManager inicializado. Testnet: {self.testnet}, Categoria: {self.category}")
        
        try:
            server_time_response = self.get_server_time_raw() # Usar método que retorna a resposta bruta
            if server_time_response and server_time_response.get('retCode') == 0:
                print("Conexão com a API Bybit (tempo do servidor) bem-sucedida.")
            else:
                print(f"ERRO: Falha ao obter tempo do servidor na inicialização. Resposta: {server_time_response}")
                print("Verifique suas chaves API, conectividade e se a conta está configurada corretamente (ex: Unificada).")
        except Exception as e:
            print(f"ERRO CRÍTICO na inicialização ao conectar à API Bybit: {e}")
            traceback.print_exc()

    def _handle_response(self, response: dict, action: str = "ação da API"):
        """Processa a resposta da API, verificando erros e retornando o resultado."""
        if response is None: # Caso a chamada da API falhe antes de obter uma resposta JSON
            print(f"ERRO ao realizar {action}: Nenhuma resposta recebida da API (a chamada pode ter falhado).")
            return None

        if response.get('retCode') == 0:
            return response.get('result')
        else:
            error_code = response.get('retCode')
            error_msg = response.get('retMsg')
            ret_ext_info = response.get('retExtInfo', {}) # Informações extendidas de erro
            print(f"ERRO ao realizar {action}: Código {error_code} - Mensagem: '{error_msg}'")
            if ret_ext_info:
                print(f"  Informação Extra: {json.dumps(ret_ext_info, indent=2)}")
            if error_msg and 'Account not unified account' in error_msg:
                print("  DICA: Por favor, verifique se sua conta Bybit é uma Conta de Trading Unificada (UTA).")
            return None

    def get_server_time_raw(self):
        """Obtém o tempo do servidor da Bybit (resposta bruta)."""
        try:
            return self.client.get_server_time()
        except Exception as e:
            print(f"EXCEÇÃO ao chamar get_server_time: {e}")
            traceback.print_exc()
            return {"retCode": -1, "retMsg": f"Exceção na chamada da API: {e}", "result": None}


    def get_server_time(self):
        """Obtém o tempo atual do servidor da Bybit (resultado processado)."""
        response = self.get_server_time_raw()
        return self._handle_response(response, "obter tempo do servidor")

    def get_account_balance(self, coin_target: str = 'USDT') -> float:
        """ Obtém o saldo da conta. Para UNIFIED, busca a moeda específica. """
        try:
            response = self.client.get_wallet_balance(accountType="UNIFIED")
        except Exception as e:
            print(f"EXCEÇÃO ao chamar get_wallet_balance: {e}")
            traceback.print_exc()
            return 0.0
            
        # Log da resposta bruta completa para depuração, independente do resultado
        print(f"DEBUG: Resposta BRUTA de get_wallet_balance: {json.dumps(response, indent=2)}")
        
        result = self._handle_response(response, f"obter saldo da conta para {coin_target}")

        if result and result.get('list'):
            for account_details in result['list']: 
                # A 'list' em contas UNIFIED geralmente tem um dicionário principal
                # que contém uma sub-lista chamada 'coin' com os detalhes de cada ativo.
                if 'coin' in account_details and isinstance(account_details['coin'], list):
                    for coin_data in account_details['coin']:
                        if coin_data.get('coin') == coin_target:
                            # Log detalhado dos dados brutos da moeda encontrada
                            print(f"DEBUG: Dados brutos encontrados para a moeda '{coin_target}': {json.dumps(coin_data, indent=2)}")
                            
                            balance_to_convert_str = None # String que será convertida para float
                            
                            # Prioridade 1: 'walletBalance' (saldo total da moeda na carteira)
                            wallet_balance_str = coin_data.get('walletBalance')
                            if wallet_balance_str and wallet_balance_str.strip(): # Verifica se existe e não é só espaços
                                balance_to_convert_str = wallet_balance_str
                                print(f"DEBUG: Usando 'walletBalance' ('{balance_to_convert_str}') para {coin_target}.")
                            
                            # Prioridade 2: 'equity' (se walletBalance não for utilizável ou não existir)
                            if not balance_to_convert_str: 
                                equity_str = coin_data.get('equity')
                                if equity_str and equity_str.strip():
                                    balance_to_convert_str = equity_str
                                    print(f"DEBUG: Usando 'equity' ('{balance_to_convert_str}') para {coin_target} (walletBalance não foi usado).")

                            # Prioridade 3: 'availableToWithdraw' (como último recurso)
                            # Nota: este campo frequentemente é vazio ou não representa o saldo total de trading.
                            if not balance_to_convert_str:
                                available_str = coin_data.get('availableToWithdraw')
                                if available_str and available_str.strip():
                                    balance_to_convert_str = available_str
                                    print(f"DEBUG: Usando 'availableToWithdraw' ('{balance_to_convert_str}') para {coin_target} (outros campos não foram usados).")
                            
                            # Tenta a conversão se uma string de saldo foi selecionada
                            if balance_to_convert_str:
                                try:
                                    balance_float = float(balance_to_convert_str)
                                    print(f"DEBUG: Saldo final para {coin_target} convertido para float: {balance_float}")
                                    return balance_float
                                except ValueError:
                                    print(f"ERRO DE CONVERSÃO: Não foi possível converter o valor '{balance_to_convert_str}' para float para a moeda {coin_target}.")
                                    return 0.0 # Retorna 0.0 em caso de falha na conversão
                            else:
                                print(f"AVISO: Nenhum campo de saldo utilizável (walletBalance, equity, availableToWithdraw) continha um valor para {coin_target}.")
                                return 0.0 # Retorna 0.0 se nenhum valor de saldo foi encontrado
            
            # Se o loop terminar sem encontrar a moeda_target específica
            print(f"AVISO: Moeda específica '{coin_target}' não encontrada na lista de moedas da conta.")
            # Você poderia, opcionalmente, tentar retornar um saldo geral da conta aqui (totalAvailableBalance),
            # mas isso geralmente é em USD e pode não ser o que se espera para um 'coin_target' específico.
            # Para maior clareza, se a moeda específica não for encontrada, retornamos 0.0.

        elif result and not result.get('list'):
             print(f"AVISO: A resposta da API para saldo da conta ('get_wallet_balance') continha uma lista vazia em 'result.list'.")
        elif not result: # Se _handle_response retornou None
             print(f"AVISO: Falha ao processar a resposta da API para saldo da conta (o resultado de _handle_response foi None).")

        print(f"ERRO FINAL: Não foi possível determinar um saldo válido para {coin_target} após verificar a resposta da API.")
        return 0.0

    def get_latest_price(self, symbol: str) -> float:
        try:
            response = self.client.get_tickers(category=self.category, symbol=symbol)
        except Exception as e:
            print(f"EXCEÇÃO ao chamar get_tickers para {symbol}: {e}")
            traceback.print_exc()
            return 0.0
            
        result = self._handle_response(response, f"obter último preço de {symbol}")
        if result and result.get('list'):
            return float(result['list'][0].get('lastPrice', 0))
        print(f"Aviso: Não foi possível obter o último preço para {symbol}.")
        return 0.0

    def set_leverage(self, symbol: str, buy_leverage: int, sell_leverage: int):
        """ Define a alavancagem. Para Cross Margin em USDT Perp, afeta a alavancagem da conta USDT. """
        print(f"DEBUG: Tentando definir alavancagem para {symbol} com buy={buy_leverage}, sell={sell_leverage}")
        try:
            response = self.client.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=str(buy_leverage),
                sellLeverage=str(sell_leverage)
            )
        except Exception as e:
            print(f"EXCEÇÃO ao chamar set_leverage para {symbol}: {e}")
            traceback.print_exc()
            return None
            
        print(f"DEBUG: Resposta BRUTA da API (set_leverage): {json.dumps(response, indent=2)}")
        return self._handle_response(response, f"definir alavancagem para {symbol} em {buy_leverage}x/{sell_leverage}x")
        
    def place_market_order(self, symbol: str, side: str, qty: float,
                           market_unit: str = "baseCoin", # "baseCoin" ou "quoteCoin"
                           reduce_only: bool = False, close_on_trigger: bool = False,
                           stop_loss_price: float = None, take_profit_price: float = None):
        if qty <= 0:
            print(f"AVISO: Quantidade ({qty}) inválida para ordem de mercado em {symbol}.")
            return None

        sltp_params = {}
        if stop_loss_price is not None and stop_loss_price > 0:
            sltp_params['stopLoss'] = str(round(stop_loss_price,6)) # Arredondar para evitar problemas de precisão
        if take_profit_price is not None and take_profit_price > 0:
            sltp_params['takeProfit'] = str(round(take_profit_price,6))

        order_params = {
            "category": self.category,
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "marketUnit": market_unit,
            "reduceOnly": reduce_only,
            "closeOnTrigger": close_on_trigger,
            **sltp_params
        }
        
        print(f"DEBUG: Enviando parâmetros para place_order: {json.dumps(order_params, indent=2)}")
        raw_response_data = None 
        try:
            # A chamada real para a API
            raw_response_data = self.client.place_order(**order_params)
            print(f"DEBUG: Resposta BRUTA da API (place_order): {json.dumps(raw_response_data, indent=2)}")
        except Exception as e:
            print(f"EXCEÇÃO CRÍTICA durante a chamada self.client.place_order: {e}")
            traceback.print_exc()
            if hasattr(e, 'args') and e.args:
                 print(f"DEBUG: Argumentos da exceção (pode conter info da resposta): {e.args}")
            # Mesmo que haja uma exceção, se raw_response_data foi preenchido (pouco provável aqui),
            # _handle_response tentaria processá-lo. Mas é mais seguro retornar None.
            return None

        return self._handle_response(raw_response_data, f"ordem de mercado {side} {qty} {symbol}")

    def get_open_positions(self, symbol: str = None):
        """
        Obtém todas as posições abertas ou uma posição específica.
        Para categoria 'linear' sem símbolo, usa settleCoin='USDT'.
        """
        params = {"category": self.category}
        action_description = "posições abertas"

        if symbol:
            params["symbol"] = symbol
            action_description += f" para {symbol}"
        elif self.category == 'linear':
            # Para a categoria 'linear' (ex: USDT perpétuos), se nenhum símbolo específico é pedido,
            # a API requer 'settleCoin' para listar todas as posições dessa moeda de liquidação.
            params["settleCoin"] = "USDT" 
            action_description += f" para {self.category} (liquidadas em USDT)"
        # Você pode adicionar 'elif' para outras categorias se elas tiverem requisitos similares
        # ex: elif self.category == 'inverse': params["settleCoin"] = "BTC" # ou outra moeda base
        else:
            action_description += f" para {self.category}" # Para categorias como 'spot', pode não precisar

        print(f"DEBUG: Parâmetros para self.client.get_positions: {json.dumps(params)}")
        try:
            response = self.client.get_positions(**params)
        except Exception as e:
            print(f"EXCEÇÃO ao chamar self.client.get_positions com params={json.dumps(params)}: {e}")
            traceback.print_exc()
            return [] # Retorna lista vazia em caso de exceção na chamada

        # O processamento da resposta continua como antes
        result = self._handle_response(response, action_description)
        if result and result.get('list'):
            # Filtra apenas posições com size > 0 (as que realmente importam)
            active_positions = [pos for pos in result['list'] if float(pos.get('size', 0)) > 0]
            return active_positions
        return []

    def get_open_orders(self, symbol: str = None):
        try:
            response = self.client.get_open_orders(category=self.category, symbol=symbol)
        except Exception as e:
            print(f"EXCEÇÃO ao chamar get_open_orders para {symbol if symbol else 'todos'}: {e}")
            traceback.print_exc()
            return []
        result = self._handle_response(response, f"ordens abertas para {symbol if symbol else 'todos'}")
        if result and result.get('list'):
            return result['list']
        return []

    def cancel_all_orders(self, symbol: str = None):
        try:
            response = self.client.cancel_all_orders(category=self.category, symbol=symbol)
        except Exception as e:
            print(f"EXCEÇÃO ao chamar cancel_all_orders para {symbol if symbol else 'todos'}: {e}")
            traceback.print_exc()
            return None
        print(f"DEBUG: Resposta BRUTA da API (cancel_all_orders): {json.dumps(response, indent=2)}")
        return self._handle_response(response, f"cancelar todas as ordens para {symbol if symbol else 'todos'}")

    def cancel_order_by_id(self, symbol: str, order_id: str):
        try:
            response = self.client.cancel_order(
                category=self.category,
                symbol=symbol,
                orderId=order_id
            )
        except Exception as e:
            print(f"EXCEÇÃO ao chamar cancel_order para {order_id} em {symbol}: {e}")
            traceback.print_exc()
            return None
        return self._handle_response(response, f"cancelar ordem {order_id} para {symbol}")
    
    # --- Função para monitorar posições em aberto ---
    def monitor_all_open_positions(self, interval_seconds: int = 10):
        """
        Monitora e exibe todas as posições abertas continuamente.
        Args:
            interval_seconds (int): Intervalo em segundos entre as atualizações.
        """
        print("\n--- INICIANDO MONITORAMENTO DE POSIÇÕES ABERTAS ---")
        print(f"Atualizando a cada {interval_seconds} segundos. Pressione CTRL+C para parar.")
        
        try:
            while True:
                print(f"\n>>> Buscando posições em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                positions = self.get_open_positions() # Chama o método existente para buscar todas as posições

                if positions:
                    print(f"Encontradas {len(positions)} posição(ões) aberta(s):")
                    for i, pos in enumerate(positions):
                        symbol = pos.get('symbol', 'N/A')
                        side = pos.get('side', 'N/A')
                        size = pos.get('size', '0')
                        leverage = pos.get('leverage', 'N/A')
                        entry_price = pos.get('avgPrice', 'N/A') 
                        mark_price = pos.get('markPrice', 'N/A')
                        unrealised_pnl = pos.get('unrealisedPnl', '0')
                        position_value = pos.get('positionValue', 'N/A')
                        liq_price = pos.get('liqPrice', '') # Pode ser vazio, especialmente em Cross Margin
                        
                        print(f"\n--- Posição {i+1}/{len(positions)} ---")
                        print(f"  Símbolo:         {symbol}")
                        print(f"  Lado:            {side}")
                        print(f"  Tamanho:         {size}")
                        print(f"  Alavancagem:     {leverage}x")
                        print(f"  Preço Entrada:   {entry_price}")
                        print(f"  Preço Marcação:  {mark_price}")
                        print(f"  P&L Não Real.:   {unrealised_pnl} USDT") # Para lineares, P&L é em USDT
                        print(f"  Valor da Posição:{position_value} USDT")
                        print(f"  Preço Liq.:      {liq_price if liq_price else 'N/A (Verifique na plataforma)'}")
                    print("--- Fim da lista de posições ---")
                else:
                    print("Nenhuma posição aberta encontrada.")
                
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\n--- MONITORAMENTO DE POSIÇÕES INTERROMPIDO PELO USUÁRIO ---")
        except Exception as e:
            print(f"ERRO DURANTE O MONITORAMENTO DE POSIÇÕES: {e}")
            traceback.print_exc()

    def run_positions_monitoring_to_json(self, output_json_file: str, interval_seconds: int = 10):
        """
        Monitora e salva todas as posições abertas em um arquivo JSON continuamente.
        Args:
            output_json_file (str): Caminho completo para o arquivo JSON de saída.
            interval_seconds (int): Intervalo em segundos entre as atualizações.
        """
        print(f"\n--- INICIANDO ESCRITA DE POSIÇÕES BYBIT PARA O ARQUIVO: {output_json_file} ---")
        print(f"Atualizando a cada {interval_seconds} segundos. Pressione CTRL+C para parar.")

        fields_to_extract = [
            "symbol", "side", "size", "leverage", 
            "avgPrice", "markPrice", "unrealisedPnl", 
            "positionValue", "liqPrice"
            # Adicione ou remova campos conforme sua necessidade para o dashboard
        ]

        try:
            while True:
                # print(f">>> Coletando dados de posições Bybit em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                raw_positions = self.get_open_positions() # Lista de dicionários

                positions_for_json = []
                if raw_positions:
                    for pos in raw_positions:
                        filtered_pos = {field: pos.get(field) for field in fields_to_extract}
                        # Certifique-se que os números estão como números ou strings que o Dash pode formatar
                        # A API da Bybit geralmente retorna números como strings, o que é ok para JSON.
                        # Se precisar converter para float/int antes de salvar:
                        # try:
                        #     filtered_pos['size'] = float(pos.get('size', 0))
                        #     filtered_pos['unrealisedPnl'] = float(pos.get('unrealisedPnl', 0))
                        #     # ... outras conversões ...
                        # except ValueError:
                        #     print(f"Aviso: erro ao converter dados para a posição {pos.get('symbol')}")
                        positions_for_json.append(filtered_pos)

                try:
                    with open(output_json_file, "w") as f:
                        json.dump(positions_for_json, f, indent=2)
                    # print(f"Dados de {len(positions_for_json)} posições salvos em {output_json_file}")
                except IOError as e:
                    print(f"ERRO DE I/O ao escrever no arquivo JSON {output_json_file}: {e}")
                except Exception as e_json:
                    print(f"ERRO inesperado ao processar ou serializar posições para JSON: {e_json}")
                    traceback.print_exc()

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print(f"\n--- ESCRITA DE POSIÇÕES PARA {output_json_file} INTERROMPIDA ---")
        except Exception as e_loop:
            print(f"ERRO CRÍTICO NO LOOP DE MONITORAMENTO PARA JSON: {e_loop}")
            traceback.print_exc()

# --- Exemplo de Uso e Teste ---
if __name__ == "__main__":
    print("--- INICIANDO O MONITOR DE POSIÇÕES BYBIT ---")

    # Carrega as variáveis de ambiente do arquivo .env
    load_dotenv()

    # Determina o modo (Testnet ou Mainnet) a partir da variável de ambiente
    # O valor padrão é 'true' se a variável não estiver definida
    testnet_mode_str = os.getenv("TESTNET", "true").lower()
    IS_TESTNET = testnet_mode_str == 'true'

    # Seleciona as chaves de API corretas com base no modo
    if IS_TESTNET:
        api_key = os.getenv("BYBIT_API_KEY_TESTNET")
        api_secret = os.getenv("BYBIT_API_SECRET_TESTNET")
        print("Modo: TESTNET")
    else:
        api_key = os.getenv("BYBIT_API_KEY_MAINNET")
        api_secret = os.getenv("BYBIT_API_SECRET_MAINNET")
        print("Modo: MAINNET (REAL)")

    # Validação das chaves de API
    if not api_key or not api_secret:
        print("\nERRO CRÍTICO: Chaves de API não encontradas no ambiente.")
        print("Por favor, crie um arquivo .env (a partir do .env.example) e defina suas chaves.")
        print("Exemplo para Testnet:")
        print('  TESTNET="true"')
        print('  BYBIT_API_KEY_TESTNET="SUA_CHAVE_TESTNET"')
        print('  BYBIT_API_SECRET_TESTNET="SEU_SEGREDO_TESTNET"')
        exit()

    # Inicializa o gerenciador de trade
    trade_manager = BybitTradeManager(
        api_key=api_key,
        api_secret=api_secret,
        testnet=IS_TESTNET,
        category=TRADE_CATEGORY
    )

    # Verifica a conexão e o saldo antes de iniciar o monitoramento
    print("\nVerificando conexão e saldo...")
    server_time_data = trade_manager.get_server_time()
    if server_time_data:
        print(f"Tempo do Servidor Bybit: {datetime.fromtimestamp(int(server_time_data['timeSecond']))}")
        balance = trade_manager.get_account_balance('USDT')
        print(f"Saldo da conta (USDT): {balance}")

        # Inicia o loop principal de monitoramento que salva as posições em JSON
        print(f"\nIniciando coletor de dados de posições da Bybit para o arquivo: {BYBIT_POSITIONS_JSON_FILE}")
        print("O script ficará rodando para atualizar o arquivo JSON. Pressione CTRL+C para parar.")
        trade_manager.run_positions_monitoring_to_json(
            output_json_file=BYBIT_POSITIONS_JSON_FILE,
            interval_seconds=7
        )
    else:
        print("\nERRO: Não foi possível conectar à API da Bybit. Verifique suas chaves e conexão.")
        print("O monitoramento de posições não será iniciado.")

    print("\n--- SCRIPT BYBIT TRADE MANAGER FINALIZADO (ou interrompido) ---")
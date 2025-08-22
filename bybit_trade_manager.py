# bybit_trade_manager.py
import pybit
from pybit.unified_trading import HTTP
import os
import time
from datetime import datetime
import json
from dotenv import load_dotenv

# --- Importações de Módulos Locais ---
from logger_config import logger
import config

# --- DEFINIÇÃO GLOBAL DO CAMINHO DO ARQUIVO JSON ---
SCRIPT_DIR_BTM = os.path.dirname(os.path.abspath(__file__))
BYBIT_POSITIONS_JSON_FILE = os.path.join(SCRIPT_DIR_BTM, 'bybit_positions.json')
# --- FIM DA DEFINIÇÃO GLOBAL ---

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
        logger.info(f"BybitTradeManager inicializado. Testnet: {self.testnet}, Categoria: {self.category}")
        
        try:
            server_time_response = self.get_server_time_raw()
            if server_time_response and server_time_response.get('retCode') == 0:
                logger.info("Conexão com a API Bybit (tempo do servidor) bem-sucedida.")
            else:
                logger.error(f"Falha ao obter tempo do servidor na inicialização. Resposta: {server_time_response}")
                logger.warning("Verifique suas chaves API, conectividade e se a conta está configurada corretamente (ex: Unificada).")
        except Exception as e:
            logger.critical(f"ERRO CRÍTICO na inicialização ao conectar à API Bybit: {e}", exc_info=True)

    def _handle_response(self, response: dict, action: str = "ação da API"):
        """Processa a resposta da API, verificando erros e retornando o resultado."""
        if response is None:
            logger.error(f"Ao realizar {action}: Nenhuma resposta recebida da API (a chamada pode ter falhado).")
            return None

        if response.get('retCode') == 0:
            return response.get('result')
        else:
            error_code = response.get('retCode')
            error_msg = response.get('retMsg')
            ret_ext_info = response.get('retExtInfo', {})
            logger.error(f"Ao realizar {action}: Código {error_code} - Mensagem: '{error_msg}'")
            if ret_ext_info:
                logger.error(f"  Informação Extra: {json.dumps(ret_ext_info, indent=2)}")
            if error_msg and 'Account not unified account' in error_msg:
                logger.warning("DICA: Por favor, verifique se sua conta Bybit é uma Conta de Trading Unificada (UTA).")
            return None

    def get_server_time_raw(self):
        """Obtém o tempo do servidor da Bybit (resposta bruta)."""
        try:
            return self.client.get_server_time()
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar get_server_time: {e}", exc_info=True)
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
            logger.error(f"EXCEÇÃO ao chamar get_wallet_balance: {e}", exc_info=True)
            return 0.0
            
        logger.debug(f"Resposta BRUTA de get_wallet_balance: {json.dumps(response, indent=2)}")
        
        result = self._handle_response(response, f"obter saldo da conta para {coin_target}")

        if result and result.get('list'):
            for account_details in result['list']:
                if 'coin' in account_details and isinstance(account_details['coin'], list):
                    for coin_data in account_details['coin']:
                        if coin_data.get('coin') == coin_target:
                            logger.debug(f"Dados brutos encontrados para a moeda '{coin_target}': {json.dumps(coin_data, indent=2)}")
                            
                            balance_to_convert_str = None
                            
                            wallet_balance_str = coin_data.get('walletBalance')
                            if wallet_balance_str and wallet_balance_str.strip():
                                balance_to_convert_str = wallet_balance_str
                                logger.debug(f"Usando 'walletBalance' ('{balance_to_convert_str}') para {coin_target}.")
                            
                            if not balance_to_convert_str: 
                                equity_str = coin_data.get('equity')
                                if equity_str and equity_str.strip():
                                    balance_to_convert_str = equity_str
                                    logger.debug(f"Usando 'equity' ('{balance_to_convert_str}') para {coin_target}.")

                            if not balance_to_convert_str:
                                available_str = coin_data.get('availableToWithdraw')
                                if available_str and available_str.strip():
                                    balance_to_convert_str = available_str
                                    logger.debug(f"Usando 'availableToWithdraw' ('{balance_to_convert_str}') para {coin_target}.")
                            
                            if balance_to_convert_str:
                                try:
                                    balance_float = float(balance_to_convert_str)
                                    logger.debug(f"Saldo final para {coin_target} convertido para float: {balance_float}")
                                    return balance_float
                                except ValueError:
                                    logger.error(f"Não foi possível converter o valor '{balance_to_convert_str}' para float para a moeda {coin_target}.")
                                    return 0.0
                            else:
                                logger.warning(f"Nenhum campo de saldo utilizável (walletBalance, equity, availableToWithdraw) continha um valor para {coin_target}.")
                                return 0.0
            
            logger.warning(f"Moeda específica '{coin_target}' não encontrada na lista de moedas da conta.")

        elif result and not result.get('list'):
             logger.warning("A resposta da API para saldo da conta ('get_wallet_balance') continha uma lista vazia em 'result.list'.")
        elif not result:
             logger.warning("Falha ao processar a resposta da API para saldo da conta (o resultado de _handle_response foi None).")

        logger.error(f"Não foi possível determinar um saldo válido para {coin_target} após verificar a resposta da API.")
        return 0.0

    def get_latest_price(self, symbol: str) -> float:
        try:
            response = self.client.get_tickers(category=self.category, symbol=symbol)
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar get_tickers para {symbol}: {e}", exc_info=True)
            return 0.0
            
        result = self._handle_response(response, f"obter último preço de {symbol}")
        if result and result.get('list'):
            return float(result['list'][0].get('lastPrice', 0))
        logger.warning(f"Não foi possível obter o último preço para {symbol}.")
        return 0.0

    def set_leverage(self, symbol: str, buy_leverage: int, sell_leverage: int):
        """ Define a alavancagem. Para Cross Margin em USDT Perp, afeta a alavancagem da conta USDT. """
        logger.debug(f"Tentando definir alavancagem para {symbol} com buy={buy_leverage}, sell={sell_leverage}")
        try:
            response = self.client.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=str(buy_leverage),
                sellLeverage=str(sell_leverage)
            )
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar set_leverage para {symbol}: {e}", exc_info=True)
            return None
            
        logger.debug(f"Resposta BRUTA da API (set_leverage): {json.dumps(response, indent=2)}")
        return self._handle_response(response, f"definir alavancagem para {symbol} em {buy_leverage}x/{sell_leverage}x")
        
    def place_market_order(self, symbol: str, side: str, qty: float,
                           market_unit: str = "baseCoin",
                           reduce_only: bool = False, close_on_trigger: bool = False,
                           stop_loss_price: float = None, take_profit_price: float = None):
        if qty <= 0:
            logger.warning(f"Quantidade ({qty}) inválida para ordem de mercado em {symbol}.")
            return None

        sltp_params = {}
        if stop_loss_price is not None and stop_loss_price > 0:
            sltp_params['stopLoss'] = str(round(stop_loss_price,6))
        if take_profit_price is not None and take_profit_price > 0:
            sltp_params['takeProfit'] = str(round(take_profit_price,6))

        order_params = {
            "category": self.category, "symbol": symbol, "side": side,
            "orderType": "Market", "qty": str(qty), "marketUnit": market_unit,
            "reduceOnly": reduce_only, "closeOnTrigger": close_on_trigger,
            **sltp_params
        }
        
        logger.debug(f"Enviando parâmetros para place_order: {json.dumps(order_params, indent=2)}")
        raw_response_data = None 
        try:
            raw_response_data = self.client.place_order(**order_params)
            logger.debug(f"Resposta BRUTA da API (place_order): {json.dumps(raw_response_data, indent=2)}")
        except Exception as e:
            logger.critical(f"EXCEÇÃO durante a chamada self.client.place_order: {e}", exc_info=True)
            if hasattr(e, 'args') and e.args:
                 logger.debug(f"Argumentos da exceção: {e.args}")
            return None

        return self._handle_response(raw_response_data, f"ordem de mercado {side} {qty} {symbol}")

    def get_open_positions(self, symbol: str = None):
        """Obtém todas as posições abertas ou uma posição específica."""
        params = {"category": self.category}
        action_description = "posições abertas"

        if symbol:
            params["symbol"] = symbol
            action_description += f" para {symbol}"
        elif self.category == 'linear':
            params["settleCoin"] = "USDT" 
            action_description += f" para {self.category} (liquidadas em USDT)"
        else:
            action_description += f" para {self.category}"

        logger.debug(f"Parâmetros para self.client.get_positions: {json.dumps(params)}")
        try:
            response = self.client.get_positions(**params)
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar self.client.get_positions com params={json.dumps(params)}: {e}", exc_info=True)
            return []

        result = self._handle_response(response, action_description)
        if result and result.get('list'):
            active_positions = [pos for pos in result['list'] if float(pos.get('size', 0)) > 0]
            return active_positions
        return []

    def get_open_orders(self, symbol: str = None):
        try:
            response = self.client.get_open_orders(category=self.category, symbol=symbol)
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar get_open_orders para {symbol if symbol else 'todos'}: {e}", exc_info=True)
            return []
        result = self._handle_response(response, f"ordens abertas para {symbol if symbol else 'todos'}")
        if result and result.get('list'):
            return result['list']
        return []

    def cancel_all_orders(self, symbol: str = None):
        try:
            response = self.client.cancel_all_orders(category=self.category, symbol=symbol)
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar cancel_all_orders para {symbol if symbol else 'todos'}: {e}", exc_info=True)
            return None
        logger.debug(f"Resposta BRUTA da API (cancel_all_orders): {json.dumps(response, indent=2)}")
        return self._handle_response(response, f"cancelar todas as ordens para {symbol if symbol else 'todos'}")

    def cancel_order_by_id(self, symbol: str, order_id: str):
        try:
            response = self.client.cancel_order(
                category=self.category,
                symbol=symbol,
                orderId=order_id
            )
        except Exception as e:
            logger.error(f"EXCEÇÃO ao chamar cancel_order para {order_id} em {symbol}: {e}", exc_info=True)
            return None
        return self._handle_response(response, f"cancelar ordem {order_id} para {symbol}")
    
    def monitor_all_open_positions(self, interval_seconds: int = 10):
        """Monitora e exibe todas as posições abertas continuamente."""
        logger.info("--- INICIANDO MONITORAMENTO DE POSIÇÕES ABERTAS ---")
        logger.info(f"Atualizando a cada {interval_seconds} segundos. Pressione CTRL+C para parar.")
        
        try:
            while True:
                logger.info(f"Buscando posições em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                positions = self.get_open_positions()

                if positions:
                    logger.info(f"Encontradas {len(positions)} posição(ões) aberta(s):")
                    pos_info = []
                    for pos in positions:
                        pos_info.append(
                            f"  Símbolo: {pos.get('symbol', 'N/A')}, "
                            f"Lado: {pos.get('side', 'N/A')}, "
                            f"Tamanho: {pos.get('size', '0')}, "
                            f"Alavancagem: {pos.get('leverage', 'N/A')}x, "
                            f"Preço Entrada: {pos.get('avgPrice', 'N/A')}, "
                            f"P&L Não Real.: {pos.get('unrealisedPnl', '0')} USDT"
                        )
                    logger.info("\n".join(pos_info))
                else:
                    logger.info("Nenhuma posição aberta encontrada.")
                
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("--- MONITORAMENTO DE POSIÇÕES INTERROMPIDO PELO USUÁRIO ---")
        except Exception as e:
            logger.error(f"ERRO DURANTE O MONITORAMENTO DE POSIÇÕES: {e}", exc_info=True)

    def run_positions_monitoring_to_json(self, output_json_file: str, interval_seconds: int = 10):
        """Monitora e salva todas as posições abertas em um arquivo JSON continuamente."""
        logger.info(f"Iniciando escrita de posições Bybit para o arquivo: {output_json_file}")
        logger.info(f"Atualizando a cada {interval_seconds} segundos. Pressione CTRL+C para parar.")

        fields_to_extract = [
            "symbol", "side", "size", "leverage", 
            "avgPrice", "markPrice", "unrealisedPnl", 
            "positionValue", "liqPrice"
        ]

        try:
            while True:
                raw_positions = self.get_open_positions()
                positions_for_json = [{field: pos.get(field) for field in fields_to_extract} for pos in raw_positions]

                try:
                    with open(output_json_file, "w") as f:
                        json.dump(positions_for_json, f, indent=2)
                    logger.debug(f"Dados de {len(positions_for_json)} posições salvos em {output_json_file}")
                except IOError as e:
                    logger.error(f"Erro de I/O ao escrever no arquivo JSON {output_json_file}: {e}")
                except Exception as e_json:
                    logger.error(f"Erro inesperado ao processar ou serializar posições para JSON: {e_json}", exc_info=True)

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info(f"--- Escrita de posições para {output_json_file} INTERROMPIDA ---")
        except Exception as e_loop:
            logger.critical(f"ERRO CRÍTICO NO LOOP DE MONITORAMENTO PARA JSON: {e_loop}", exc_info=True)

# --- Exemplo de Uso e Teste ---
if __name__ == "__main__":
    logger.info("--- INICIANDO O MONITOR DE POSIÇÕES BYBIT ---")

    load_dotenv()

    testnet_mode_str = os.getenv("TESTNET", "true").lower()
    IS_TESTNET = testnet_mode_str == 'true'

    if IS_TESTNET:
        api_key = os.getenv("BYBIT_API_KEY_TESTNET")
        api_secret = os.getenv("BYBIT_API_SECRET_TESTNET")
        logger.info("Modo: TESTNET")
    else:
        api_key = os.getenv("BYBIT_API_KEY_MAINNET")
        api_secret = os.getenv("BYBIT_API_SECRET_MAINNET")
        logger.info("Modo: MAINNET (REAL)")

    if not api_key or not api_secret:
        logger.critical("Chaves de API não encontradas no ambiente.")
        logger.critical("Por favor, crie um arquivo .env (a partir do .env.example) e defina suas chaves.")
        exit()

    trade_manager = BybitTradeManager(
        api_key=api_key,
        api_secret=api_secret,
        testnet=IS_TESTNET,
        category=config.TRADE_CATEGORY
    )

    logger.info("Verificando conexão e saldo...")
    server_time_data = trade_manager.get_server_time()
    if server_time_data:
        logger.info(f"Tempo do Servidor Bybit: {datetime.fromtimestamp(int(server_time_data['timeSecond']))}")
        balance = trade_manager.get_account_balance('USDT')
        logger.info(f"Saldo da conta (USDT): {balance}")

        logger.info(f"Iniciando coletor de dados de posições da Bybit para o arquivo: {BYBIT_POSITIONS_JSON_FILE}")
        trade_manager.run_positions_monitoring_to_json(
            output_json_file=BYBIT_POSITIONS_JSON_FILE,
            interval_seconds=7
        )
    else:
        logger.error("Não foi possível conectar à API da Bybit. Verifique suas chaves e conexão.")
        logger.error("O monitoramento de posições não será iniciado.")

    logger.info("--- SCRIPT BYBIT TRADE MANAGER FINALIZADO (ou interrompido) ---")
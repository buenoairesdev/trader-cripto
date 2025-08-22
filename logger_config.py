import logging
import sys

def setup_logger():
    """
    Configura e retorna um logger raiz para o projeto.

    Este logger envia mensagens para o console (stdout) com um formato
    que inclui o timestamp, o nível do log e a mensagem.

    Níveis de Log:
    - DEBUG: Informações detalhadas, tipicamente de interesse apenas para diagnosticar problemas.
    - INFO: Confirmação de que as coisas estão funcionando como esperado.
    - WARNING: Uma indicação de que algo inesperado aconteceu, ou um problema iminente.
    - ERROR: Devido a um problema mais sério, o software não foi capaz de executar alguma função.
    - CRITICAL: Um erro sério, indicando que o programa pode não conseguir continuar rodando.
    """
    # Cria um logger
    logger = logging.getLogger("CryptoTrader")

    # Previne que handlers sejam adicionados múltiplas vezes se a função for chamada de novo
    if not logger.handlers:
        logger.setLevel(logging.INFO) # Define o nível de log mais baixo a ser processado

        # Cria um handler para o console
        console_handler = logging.StreamHandler(sys.stdout)

        # Cria um formatter e o adiciona ao handler
        # Formato: [TIMESTAMP] LEVEL: MESSAGE
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)

        # Adiciona o handler ao logger
        logger.addHandler(console_handler)

        # Define a propagação para False para evitar que o logger raiz do Python
        # processe as mensagens novamente, o que poderia levar a logs duplicados.
        logger.propagate = False

    return logger

# Cria uma instância global do logger para ser importada por outros módulos
logger = setup_logger()

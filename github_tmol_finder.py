#!/usr/bin/env python3
"""
Script para buscar repositórios no GitHub que contenham:
- arquivos requirements.txt com "transitions"
- arquivos .yml com "transitions"
"""

import json
import requests
import time
import os
import base64
from datetime import datetime

class GitHubRepoMiner:
    def __init__(self, token=None):
        """
        Inicializa o minerador de repositórios.
        
        :param token: Token de acesso pessoal do GitHub (opcional, mas recomendado)
        """
        self.base_url = "https://api.github.com"
        self.headers = {}
        
        # Se um token for fornecido, use-o para autenticação
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        self.headers["Accept"] = "application/vnd.github.v3+json"
        
        # Para evitar problemas de rate limit
        self.rate_limit_remaining = 1000
        
    def check_rate_limit(self):
        """Verifica os limites de taxa da API do GitHub e espera se necessário."""
        if self.rate_limit_remaining < 10:
            print("Chegando perto do limite de taxa. Verificando limites...")
            response = requests.get(f"{self.base_url}/rate_limit", headers=self.headers)
            data = response.json()
            
            self.rate_limit_remaining = data["rate"]["remaining"]
            reset_time = data["rate"]["reset"]
            
            if self.rate_limit_remaining < 5:
                wait_time = reset_time - int(time.time()) + 10
                print(f"Quase no limite! Esperando {wait_time} segundos para reset...")
                time.sleep(wait_time)
    
    def search_python_repos(self, query="language:python", page=1, per_page=30):
        """
        Busca repositórios Python com base na query fornecida.
        
        :param query: Query de busca para filtragem adicional
        :param page: Número da página dos resultados
        :param per_page: Número de resultados por página
        :return: Lista de repositórios encontrados
        """
        self.check_rate_limit()
        
        search_url = f"{self.base_url}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "page": page,
            "per_page": per_page
        }
        
        response = requests.get(search_url, headers=self.headers, params=params)
        
        if response.status_code != 200:
            print(f"Erro na busca de repositórios: {response.status_code}")
            print(response.json())
            return []
        
        self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
        data = response.json()
        
        return data.get("items", [])
    
    def search_specific_files_in_repo(self, repo_full_name, filename):
        """
        Busca arquivos específicos (como requirements.txt ou .yml) em um repositório.
        
        :param repo_full_name: Nome completo do repositório (formato: 'dono/repo')
        :param filename: Nome do arquivo ou extensão a ser buscada
        :return: Lista de arquivos encontrados
        """
        self.check_rate_limit()
        
        # Usando a API de busca de código
        search_url = f"{self.base_url}/search/code"
        
        # Construir a query apropriada
        if filename.startswith("."):  # Se for uma extensão
            query = f"extension:{filename[1:]} repo:{repo_full_name}"
        else:  # Se for um nome de arquivo específico
            query = f"filename:{filename} repo:{repo_full_name}"
        
        params = {
            "q": query,
            "per_page": 100
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.get(search_url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
                data = response.json()
                # Salvar a resposta em um arquivo JSON no diretório "output"
                output_dir = "output"
                os.makedirs(output_dir, exist_ok=True)  # Criar o diretório se não existir
                output_filename = os.path.join(output_dir, f"{repo_full_name.replace('/', '_')}_{filename.replace('.', '_')}_search_results.json")
                
                with open(output_filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                
                return data.get("items", [])
            elif response.status_code == 403 and "rate limit exceeded" in response.text:
                # Obter o tempo exato de reset do rate limit
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                current_time = int(time.time())
                wait_time = max(reset_time - current_time + 10, 60)  # Adiciona 10s de margem
                
                print(f"Limite de taxa excedido. Esperando {wait_time} segundos até o reset...")
                print(f"Tempo de reset: {datetime.fromtimestamp(reset_time).strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(wait_time)
                # Continua o loop para tentar novamente após a espera
            else:
                print(f"Erro na busca de arquivos {filename} em {repo_full_name}: {response.status_code}")
                print(response.json())
                if attempt < max_retries - 1:
                    # Backoff exponencial: esperar cada vez mais entre as tentativas
                    wait_time = (2 ** attempt) * 30
                    print(f"Tentativa {attempt+1}/{max_retries} falhou. Esperando {wait_time}s antes de tentar novamente...")
                    time.sleep(wait_time)
                else:
                    return []
        
        return []
    
    def check_file_content_for_text(self, repo_full_name, file_path, search_text):
        """
        Verifica se um arquivo contém um texto específico.
        
        :param repo_full_name: Nome completo do repositório
        :param file_path: Caminho do arquivo no repositório
        :param search_text: Texto a ser procurado no arquivo
        :return: True se o texto for encontrado, False caso contrário
        """
        self.check_rate_limit()
        
        content_url = f"{self.base_url}/repos/{repo_full_name}/contents/{file_path}"
        
        response = requests.get(content_url, headers=self.headers)
        
        if response.status_code != 200:
            print(f"Erro ao obter conteúdo do arquivo {file_path}: {response.status_code}")
            return False
        
        self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
        data = response.json()
        
        # Alguns arquivos podem ser muito grandes e não ter conteúdo direto
        if "content" not in data:
            return False
        
        try:
            # O conteúdo vem em base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return search_text.lower() in content.lower()
        except Exception as e:
            print(f"Erro ao decodificar o conteúdo do arquivo {file_path}: {str(e)}")
            return False
    
    def create_segmented_queries(self):
        """
        Cria queries segmentadas para contornar o limite de 1000 resultados da API GitHub.
        Divide as buscas por estrelas, data de criação, e data de atualização.
        
        :return: Lista de queries segmentadas
        """
        queries = []
        
        # Base da query - repositórios Python
        base_query = "language:python"
        
        # Segmentação por estrelas
        star_ranges = [
            "stars:0..10",
            "stars:11..50",
            "stars:51..100",
            "stars:101..500",
            "stars:501..1000",
            "stars:1001..5000",
            "stars:5001..10000",
            "stars:>10000"
        ]
        
        # Segmentação por data de criação (últimos 10 anos, dividido por anos)
        current_year = datetime.now().year
        years = list(range(current_year - 10, current_year + 1))
        
        # Combinações de segmentação
        for star_range in star_ranges:
            # Apenas por estrelas
            queries.append(f"{base_query} {star_range}")
            
            # Por estrelas e anos de criação
            for i in range(len(years) - 1):
                created_range = f"created:{years[i]}-01-01..{years[i+1]}-01-01"
                queries.append(f"{base_query} {star_range} {created_range}")
        
        # Adicionar algumas queries específicas para repositórios muito recentes
        queries.append(f"{base_query} created:>{years[-2]}-01-01")
        
        # Adicionar queries por tamanho para capturar diferentes tipos de projetos
        size_ranges = ["size:<1000", "size:1000..5000", "size:>5000"]
        for size_range in size_ranges:
            queries.append(f"{base_query} {size_range}")
        
        return queries
    
    def find_repos_with_criteria_segmented(self, max_repos=1000):
        """
        Busca repositórios Python com buscas segmentadas para contornar o limite de 1000 resultados.
        
        :param max_repos: Número máximo de repositórios a serem verificados no total
        :return: Dicionário com repositórios e resultados das verificações
        """
        results = {}
        repos_checked = 0
        
        # Obter queries segmentadas
        queries = self.create_segmented_queries()
        print(f"Criadas {len(queries)} queries segmentadas para busca")
        
        for query_index, query in enumerate(queries):
            if repos_checked >= max_repos:
                break
                
            print(f"\nExecutando query {query_index + 1}/{len(queries)}: {query}")
            page = 1
            
            while repos_checked < max_repos:
                print(f"Buscando página {page} com query: {query}")
                repos = self.search_python_repos(query=query, page=page, per_page=30)
                
                if not repos:
                    print("Não há mais repositórios para esta query.")
                    break
                
                for repo in repos:
                    if repos_checked >= max_repos:
                        break
                    
                    repo_name = repo["full_name"]
                    
                    # Pular repositórios já verificados
                    if repo_name in results:
                        print(f"Repositório {repo_name} já foi verificado anteriormente. Pulando...")
                        continue
                    
                    repos_checked += 1
                    print(f"[{repos_checked}/{max_repos}] Verificando {repo_name}...")
                    
                    repo_data = {
                        "repo_url": repo["html_url"],
                        "stars": repo["stargazers_count"],
                        "description": repo["description"],
                        "requirements_with_transitions": [],
                        "yml_with_transitions": []
                    }
                    
                    found_relevant_content = False
                    
                    # Buscar arquivos requirements.txt
                    req_files = self.search_specific_files_in_repo(repo_name, "requirements.txt")
                    for req_file in req_files:
                        file_path = req_file["path"]
                        if self.check_file_content_for_text(repo_name, file_path, "transitions"):
                            print(f"✓ Arquivo {file_path} contém 'transitions'!")
                            repo_data["requirements_with_transitions"].append({
                                "name": req_file["name"],
                                "path": file_path,
                                "url": req_file["html_url"]
                            })
                            found_relevant_content = True
                    
                    # Buscar arquivos .yml
                    yml_files = self.search_specific_files_in_repo(repo_name, ".yml")
                    for yml_file in yml_files:
                        file_path = yml_file["path"]
                        if self.check_file_content_for_text(repo_name, file_path, "transitions"):
                            print(f"✓ Arquivo {file_path} contém 'transitions'!")
                            repo_data["yml_with_transitions"].append({
                                "name": yml_file["name"],
                                "path": file_path,
                                "url": yml_file["html_url"]
                            })
                            found_relevant_content = True
                    
                    pyproject_files = self.search_specific_files_in_repo(repo_name, "pyproject.toml")
                    for pyproject_file in pyproject_files:
                        file_path = pyproject_file["path"]
                        if self.check_file_content_for_text(repo_name, file_path, "transitions"):
                            print(f"✓ Arquivo {file_path} contém 'transitions'!")
                            repo_data["requirements_with_transitions"].append({
                                "name": pyproject_file["name"],
                                "path": file_path,
                                "url": pyproject_file["html_url"]
                            })
                            found_relevant_content = True
                    
                    # Só incluir nos resultados se atender a pelo menos um dos critérios
                    if found_relevant_content:
                        results[repo_name] = repo_data
                
                page += 1
                
                # Se encontrarmos poucos resultados nesta página, vamos para a próxima query
                if len(repos) < 10:
                    print("Poucos resultados nesta página, avançando para a próxima query...")
                    break
                
                # Se estamos chegando ao final da query atual, vamos para a próxima
                if page > 30:  # Aproximadamente 900 resultados por query
                    print("Atingimos o limite de busca para esta query, avançando para a próxima...")
                    break
        
        return results

def save_results_to_file(results, filename="repo_search_results.txt"):
    """Salva os resultados em um arquivo de texto."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Resultados da pesquisa em repositórios Python\n")
        f.write(f"Data da pesquisa: {current_time}\n")
        f.write("-" * 80 + "\n\n")
        
        if not results:
            f.write("Nenhum repositório que atenda aos critérios foi encontrado.\n")
            return
        
        f.write(f"Total de repositórios encontrados: {len(results)}\n\n")
        
        for repo_name, repo_data in results.items():
            f.write(f"Repositório: {repo_name}\n")
            f.write(f"URL: {repo_data['repo_url']}\n")
            f.write(f"Estrelas: {repo_data['stars']}\n")
            
            if repo_data['description']:
                f.write(f"Descrição: {repo_data['description']}\n")
            
            # Arquivos requirements.txt com transitions
            if repo_data['requirements_with_transitions']:
                f.write(f"Arquivos requirements.txt com 'transitions': {len(repo_data['requirements_with_transitions'])}\n")
                for i, file_data in enumerate(repo_data['requirements_with_transitions'], 1):
                    f.write(f"  {i}. {file_data['path']} - {file_data['url']}\n")
            
            # Arquivos .yml com transitions
            if repo_data['yml_with_transitions']:
                f.write(f"Arquivos .yml com 'transitions': {len(repo_data['yml_with_transitions'])}\n")
                for i, file_data in enumerate(repo_data['yml_with_transitions'], 1):
                    f.write(f"  {i}. {file_data['path']} - {file_data['url']}\n")
            
            f.write("\n" + "-" * 80 + "\n\n")


def main():
    # Verificar se existe um token no ambiente ou pedir para o usuário
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Aviso: Nenhum token GITHUB_TOKEN encontrado nas variáveis de ambiente.")
        print("Usar a API sem autenticação tem limites de taxa muito baixos.")
        print("Recomenda-se criar um token pessoal em https://github.com/settings/tokens")
        print("Para esta implementação segmentada, um token é ALTAMENTE recomendado!")
        token_input = input("Insira seu token pessoal do GitHub (deixe em branco para continuar sem token): ").strip()
        if token_input:
            token = token_input
    
    miner = GitHubRepoMiner(token=token)
    
    max_repos = 1000
    try:
        max_input = input(f"Número máximo de repositórios a verificar (padrão: {max_repos}): ").strip()
        if max_input:
            max_repos = int(max_input)
    except ValueError:
        print(f"Valor inválido. Usando o padrão: {max_repos}")
    
    print(f"Iniciando busca segmentada em até {max_repos} repositórios Python...")
    
    # Usar a nova função com buscas segmentadas
    results = miner.find_repos_with_criteria_segmented(max_repos=max_repos)
    
    filename = "repo_search_results.txt"
    save_results_to_file(results, filename)
    
    print("\nResumo dos resultados:")
    print(f"Total de repositórios relevantes encontrados: {len(results)}")
    
    # Contagens detalhadas
    req_count = sum(1 for repo in results.values() if repo['requirements_with_transitions'])
    yml_count = sum(1 for repo in results.values() if repo['yml_with_transitions'])
    
    print(f"Repositórios com 'transitions' em requirements.txt: {req_count}")
    print(f"Repositórios com 'transitions' em arquivos .yml: {yml_count}")
    
    print(f"Os resultados completos foram salvos em '{filename}'")

if __name__ == "__main__":
    main()

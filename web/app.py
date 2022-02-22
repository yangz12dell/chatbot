import os
from pprint import pprint

from flask import Flask, render_template, jsonify, request
from elasticsearch import Elasticsearch
from bert_serving.client import BertClient
SEARCH_SIZE = 10

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/search')
def analyzer():
    client = Elasticsearch('elasticsearch:9200')

    ############ 1. Prepare data ############

    question = request.args.get('question')
    strategy = request.args.get('strategy')
    search_in = request.args.get('searchin')

    # Pattern search
    if strategy == 'pattern':
        index_name = 'pattern'
        field = 'title' if search_in == 'question' else 'text'
        query = {
            "query_string": {
                "default_field": field,
                "query": question,
                "escape": True
            }
        }
    # Semantic search
    else:
        index_name = 's_question' if search_in == 'question' else 's_answer'
        bc = BertClient(ip='bertserving', output_fmt='list')
        query_vector = bc.encode([question])[0]
        query = {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, doc['vector']) + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }

    #pprint(query)
    
    ############ 2. Send request ############

    response = client.search(
        index=index_name,
        body={
            "size": SEARCH_SIZE,
            "query": query,
            "_source": {"includes": ["title", "text"]}
        }
    )

    ############ 3. Handle response ############

    # If semantic search in answer, maybe some redundant QA pairs will be returned
    # The list is in order of descending score, so keep the first QA pair
    if strategy == 'semantic' and search_in == 'answer':
        hits = []
        sources = []
        for index in range(len(response['hits']['hits'])):
            if response['hits']['hits'][index]['_source'] not in sources:
                hits.append(response['hits']['hits'][index])
                sources.append(response['hits']['hits'][index]['_source'])

        response['hits']['hits'] = hits

    # Append strategy, searchin and question
    response['query'] = {}
    response['query']['strategy'] = strategy
    response['query']['searchin'] = search_in
    response['query']['question'] = question

    #pprint(response)
    return jsonify(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)

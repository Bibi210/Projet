import re
import nltk
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
import requests
from concurrent import futures
import subprocess


from gutendex.models import Book, BookKeyword, JaccardIndex, Keyword, Suggestions
from gutendex.serializers import BookSerializer, DetailedBookSerializer
from functools import partial
from django.core.paginator import Paginator

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Create your views here.

page_size = 32
stop_words = set(nltk.corpus.stopwords.words('english'))
stemmer = nltk.stem.SnowballStemmer('english')


def get_pagefrom_request(request):
    if 'page' in request.GET and request.GET['page'].isdigit():
        page = int(request.GET['page'])
        if page < 1:
            page = 1
        return page


def get_requested_page(request, queryset):
    page = get_pagefrom_request(request)
    paginator = Paginator(queryset, page_size)
    return paginator.get_page(page)


def calculate_score(tokens, book):
    average_tf = 0
    average_idf = 0
    for token in tokens:
        try:
            word = Keyword.objects.get(word=token)
            idf = word.idf
            tf = BookKeyword.objects.filter(book=book).get(keyword=word).repetition_percentage
            average_tf += tf
            average_idf += idf
        except (BookKeyword.DoesNotExist, Keyword.DoesNotExist):
            pass

    tokenlen = len(tokens)
    average_idf = average_idf / tokenlen
    average_tf = average_tf / tokenlen
    average_tf = 0.7 * average_tf * average_idf
    closeness_score = 0.15 * book.closeness_centrality
    betweenness_score = 0.15 * book.betweenness_centrality
    return average_tf + closeness_score + betweenness_score


def get_token(sentence):
    sentence = sentence.replace('-', ' ').replace('"', ' ')
    tokens = nltk.word_tokenize(sentence)
    tokens = [stemmer.stem(word.lower()) for word in tokens if word.isalpha()
              and word.lower() not in stop_words]
    return tokens


class TopBooks(APIView):
    def get(self, request):
        top = Book.objects.order_by('-download_count')
        serializer = BookSerializer(get_requested_page(request, top), many=True)
        return Response(serializer.data)


class SearchBook(APIView):

    def get_matching_all_tokens(_, tokens):
        queryset = Book.objects.all()
        titlebooks = Book.objects.all()
        for token in tokens:
            queryset = queryset.filter(keywords__word=token)
            titlebooks = titlebooks.filter(title__icontains=token)

        partial_apply = partial(calculate_score, tokens)
        titlebooks = titlebooks.exclude(pk__in=[b.pk for b in queryset])
        queryset = sorted(titlebooks, key=partial_apply, reverse=True) + \
            sorted(queryset, key=partial_apply, reverse=True)
        return queryset

    def search(self, tokens):
        print(f'Querying for {tokens}')
        result = self.get_matching_all_tokens(tokens)
        print(f'Queryset count: {len(result)}')
        """ If the queryset is empty, we will try to find books that have similar keywords to the ones in the sentence"""
        if len(result) == 0:
            result = Book.objects.filter(keywords__word__in=tokens)
            query = Q()
            for token in tokens:
                query |= Q(title__icontains=token)
            title_match = Book.objects.filter(query)

            print(f'Queryset count: {len(result)}')
            print(f'Title match count: {title_match.query}')
            partial_apply = partial(calculate_score, tokens)
            sorted_books = sorted(result, key=partial_apply, reverse=True)
            sorted_title_books = sorted(title_match, key=partial_apply, reverse=True)
            result = sorted_title_books + sorted_books
        return result

    def get(self, request, sentence):
        tokens = get_token(sentence)
        print(f'Querying for {tokens}')
        queryset = self.search(tokens)
        queryset = get_requested_page(request, queryset)
        serializer = BookSerializer(queryset, many=True)
        return Response(serializer.data)


class GetHighestBetweenness(APIView):
    def get(self, request):
        queryset = Book.objects.all().order_by('-betweenness_centrality')
        queryset = get_requested_page(request, queryset)
        return Response(BookSerializer(queryset, many=True).data)


class BookDetail(APIView):
    def get(self, _, pk):
        try:
            book = Book.objects.get(pk=pk)
            serializer = DetailedBookSerializer(book)
            return Response(serializer.data)
        except Book.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class Suggest(APIView):
    def get(self, request, book_id):
        queryset = Suggestions.objects.get(book_id=book_id).suggested_books.all()
        serializer = BookSerializer(get_requested_page(request, queryset), many=True)
        return Response(serializer.data)


class RegExSearch(APIView):
    def get(self, request, regex):
        """ Check regex validity"""
        try:
            re.compile(regex)
        except re.error:
            return Response(data={"error": "Invalid regex"}, status=status.HTTP_400_BAD_REQUEST)
        print(f'Querying in title for {regex}')
        result = Book.objects.filter(title__iregex=regex)
        it = Book.objects.all().difference(result).iterator()
        regex = regex.lower()

        result = list(result)
        if Keyword.objects.filter(word__iregex=regex).exists():
            while len(result) < get_pagefrom_request(request) * page_size:
                try:
                    b = next(it)
                    b.keywords.get(word__iregex=regex)
                    result.append(b)
                    print(f'Added {b.title}')

                except StopIteration:
                    break
                except Keyword.DoesNotExist:
                    pass

        result = sorted(result, key=lambda x: x.betweenness_centrality, reverse=True)
        result = get_requested_page(request, result)
        serializer = BookSerializer(result, many=True)
        return Response(serializer.data)

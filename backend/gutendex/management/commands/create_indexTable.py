import nltk
import requests
from django.core.management.base import BaseCommand
from gutendex.models import Keyword, Format, BookKeyword, Book
from django.db import transaction

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')


class Command(BaseCommand):
    help = 'Get words from books and create index table for search engine'

    def handle(self, *args, **kwargs):
        print('Deleting previous data')
        Keyword.objects.all().delete()
        BookKeyword.objects.all().delete()
        self.create_Table()

    def create_Table(self):
        stop_words = set(nltk.corpus.stopwords.words('english'))
        stemmer = nltk.stem.SnowballStemmer('english')

        batch_size = 100
        eligible_books = Book.objects.filter(formats__format_type__in=['text/plain; charset=us-ascii']).distinct()

        print(f'Processing {eligible_books.count()} books')
        for i in range(0, eligible_books.count(), batch_size):
            with transaction.atomic():
                for book in eligible_books[i:i+batch_size]:
                    format = book.formats.filter(
                        format_type__in=['text/plain; charset=us-ascii', 'text/plain; charset=utf-8']).first()
                    if not format:
                        continue
                    rawtext = requests.get(format.url).text
                    tokens = nltk.word_tokenize(rawtext)
                    tokens = [word.lower() for word in tokens if word.isalpha() and word.lower() not in stop_words]
                    tokens = [stemmer.stem(word) for word in tokens]

                    word_counts = {}
                    for word in tokens:
                        word_counts[word] = word_counts.get(word, 0) + 1

                    total_words = len(tokens)
                    book_keywords = []
                    for word, count in word_counts.items():
                        keyword, _ = Keyword.objects.get_or_create(word=word)
                        repetition_percentage = (count / total_words) * 100
                        book_keywords.append(BookKeyword(book=book, keyword=keyword,
                                             occurrences=count, repetition_percentage=repetition_percentage))

                    BookKeyword.objects.bulk_create(book_keywords, ignore_conflicts=True)
                    print("Processed book: ", book.title)

            print(f'Processed batch {i // batch_size + 1}/{(eligible_books.count() - 1) // batch_size + 1}')

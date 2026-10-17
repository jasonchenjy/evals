FROM pytest5786-runtime:py3820
WORKDIR /work
COPY src /work/src
COPY public_test.py /work/public_test.py
RUN git init -q && git add . && GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z git -c user.name=Spike -c user.email=spike@invalid -c commit.gpgsign=false commit -qm base && cp -a /work /base

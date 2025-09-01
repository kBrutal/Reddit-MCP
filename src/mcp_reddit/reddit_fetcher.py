import os
from typing import Optional
from redditwarp.ASYNC import Client
from redditwarp.models.submission_ASYNC import LinkPost, TextPost, GalleryPost
from fastmcp import FastMCP
import logging

mcp = FastMCP("Reddit MCP")

REDDIT_CLIENT_ID=os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET=os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN=os.getenv("REDDIT_REFRESH_TOKEN")

CREDS = [x for x in [REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN] if x]

client = Client(*CREDS)
logging.getLogger().setLevel(logging.WARNING)

@mcp.tool()
async def fetch_user_latest_posts(username: str, limit: int = 10, sort: str = "new") -> str:
    """
    Fetch latest posts from a specific Reddit user

    Args:
        username: Reddit username (without u/ prefix)
        limit: Number of posts to fetch (default: 10)
        sort: Sort method - 'new', 'hot', 'top' (default: 'new')

    Returns:
        Human readable string containing user's latest posts
    """
    try:
        posts = []
        
        # Try different API structures for redditwarp
        submission_iter = None
        
        # Method 1: Try client.p.user structure
        try:
            if sort == "new":
                submission_iter = client.p.user.pull.submissions.new(username, limit)
            elif sort == "hot":
                submission_iter = client.p.user.pull.submissions.hot(username, limit)
            elif sort == "top":
                submission_iter = client.p.user.pull.submissions.top(username, limit)
        except AttributeError:
            pass
        
        # Method 2: Try client.p.account structure
        if submission_iter is None:
            try:
                if sort == "new":
                    submission_iter = client.p.account.pull.submissions.new(username, limit)
                elif sort == "hot":
                    submission_iter = client.p.account.pull.submissions.hot(username, limit)
                elif sort == "top":
                    submission_iter = client.p.account.pull.submissions.top(username, limit)
            except AttributeError:
                pass
        
        # Method 3: Try using search instead
        if submission_iter is None:
            try:
                # Search for posts by author
                submission_iter = client.p.subreddit.pull.search("all", f"author:{username}", sort=sort, limit=limit)
            except AttributeError:
                return f"Unable to access user posts API. RedditWarp API structure may have changed."
        
        if submission_iter is None:
            return f"Invalid sort method: {sort}. Use 'new', 'hot', or 'top'."

        async for submission in submission_iter:
            # Format timestamp if available
            created_time = ""
            if hasattr(submission, 'created_at') and submission.created_at:
                created_time = f"Posted: {submission.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            
            post_info = (
                f"Title: {submission.title}\n"
                f"Subreddit: r/{submission.subreddit_name}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"{created_time}"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: https://reddit.com{submission.permalink}\n"
                f"Post ID: {submission.id36}\n"
                f"---"
            )
            posts.append(post_info)

        if not posts:
            return f"No posts found for user: {username}"
        
        return f"Latest {len(posts)} posts from u/{username}:\n\n" + "\n\n".join(posts)

    except Exception as e:
        logging.error(f"An error occurred while fetching posts for {username}: {str(e)}")
        return f"An error occurred while fetching posts for {username}: {str(e)}"



@mcp.tool()
async def fetch_reddit_hot_threads(subreddit: str, limit: int = 10) -> str:
    """
    Fetch hot threads from a subreddit

    Args:
        subreddit: Name of the subreddit
        limit: Number of posts to fetch (default: 10)

    Returns:
        Human readable string containing list of post information
    """
    try:
        posts = []
        async for submission in client.p.subreddit.pull.hot(subreddit, limit):
            post_info = (
                f"Title: {submission.title}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"Author: {submission.author_display_name or '[deleted]'}\n"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: https://reddit.com{submission.permalink}\n"
                f"---"
            )
            posts.append(post_info)

        return "\n\n".join(posts)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"

def _format_comment_tree(comment_node, depth: int = 0) -> str:
    """Helper method to recursively format comment tree with proper indentation"""
    comment = comment_node.value
    indent = "-- " * depth
    content = (
        f"{indent}* Author: {comment.author_display_name or '[deleted]'}\n"
        f"{indent}  Score: {comment.score}\n"
        f"{indent}  {comment.body}\n"
    )

    for child in comment_node.children:
        content += "\n" + _format_comment_tree(child, depth + 1)

    return content

@mcp.tool()
async def fetch_reddit_post_content(post_id: str, comment_limit: int = 20, comment_depth: int = 3) -> str:
    """
    Fetch detailed content of a specific post

    Args:
        post_id: Reddit post ID
        comment_limit: Number of top level comments to fetch
        comment_depth: Maximum depth of comment tree to traverse

    Returns:
        Human readable string containing post content and comments tree
    """
    try:
        submission = await client.p.submission.fetch(post_id)

        content = (
            f"Title: {submission.title}\n"
            f"Score: {submission.score}\n"
            f"Author: {submission.author_display_name or '[deleted]'}\n"
            f"Type: {_get_post_type(submission)}\n"
            f"Content: {_get_content(submission)}\n"
        )

        comments = await client.p.comment_tree.fetch(post_id, sort='top', limit=comment_limit, depth=comment_depth)
        if comments.children:
            content += "\nComments:\n"
            for comment in comments.children:
                content += "\n" + _format_comment_tree(comment)
        else:
            content += "\nNo comments found."

        return content

    except Exception as e:
        return f"An error occurred: {str(e)}"

def _get_post_type(submission) -> str:
    """Helper method to determine post type"""
    if isinstance(submission, LinkPost):
        return 'link'
    elif isinstance(submission, TextPost):
        return 'text'
    elif isinstance(submission, GalleryPost):
        return 'gallery'
    return 'unknown'

def _get_content(submission) -> Optional[str]:
    """Helper method to extract post content based on type"""
    if isinstance(submission, LinkPost):
        return submission.permalink
    elif isinstance(submission, TextPost):
        return submission.body
    elif isinstance(submission, GalleryPost):
        return str(submission.gallery_link)
    return None
